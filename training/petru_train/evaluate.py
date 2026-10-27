"""Three numbers per model and the gate comparing them: held-out loss, tool-call validity, task pass rate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from petru_train.samples import load_tools, read_jsonl, render_chat, text_tokenizer
from petru_train.server import start_server, stop, wait_healthy

TRAINING_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_DIR.parent
REQUESTS_FILE = TRAINING_DIR / "eval" / "tool_requests.json"
TASKS_DIR = TRAINING_DIR / "tasks"
TASK_LIMIT = 6  # evaluated harness tasks, taken in turn from every stack
HARNESS_VERSION = 2  # bump when the harness changes what counts as a pass
# 2 (2026-10-27): no checks = fail, plus that night's agent fixes (git log --since 2026-10-27 -- petru)
BASE_GGUF = REPO_ROOT / "infra" / "llama.cpp" / "models" / "Qwen3.5-4B.IQ4_XS.gguf"
TOOL_TOLERANCE = 0.05
EVAL_SYSTEM = (
    "You are Petru, a local coding agent in the user's terminal. Use the tools to act; "
    "answer in plain text only when no tool applies."
)
TaskRunner = Callable[[Path, str, int], dict]


@dataclass
class EvalResult:
    loss: float
    tool_validity: float
    task_pass: float
    details: dict
    signature: str = ""  # which tasks and requests were measured; "" for results saved before it existed

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> EvalResult:
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def select_eval_tasks(tasks_dir: Path, limit: int = TASK_LIMIT) -> list[Path]:
    """`limit` harness tasks taken in turn from every stack (the name prefix: python_, ts_, flutter_...), so
    each language counts the same; sorted by name."""
    stacks: dict[str, list[Path]] = {}
    for task in sorted(tasks_dir.glob("*.toml")):
        stacks.setdefault(task.stem.split("_")[0], []).append(task)
    picked: list[Path] = []
    for round_ in range(max((len(group) for group in stacks.values()), default=0)):
        for stack in sorted(stacks):
            if round_ < len(stacks[stack]) and len(picked) < limit:
                picked.append(stacks[stack][round_])
    return sorted(picked)


def tasks_signature(tasks_dir: Path, requests_file: Path, limit: int) -> str:
    """Hash of exactly what tool_validity and task_pass measure, so a stale baseline is noticed."""
    digest = hashlib.sha1(f"limit={limit} harness={HARNESS_VERSION}".encode())
    digest.update(requests_file.read_bytes() if requests_file.is_file() else b"")
    for task in select_eval_tasks(tasks_dir, limit):
        digest.update(task.name.encode("utf-8"))
        digest.update(task.read_bytes())
    return digest.hexdigest()[:16]


def gate(base: EvalResult, cand: EvalResult) -> tuple[bool, str]:
    reasons = []
    if base.signature and cand.signature and base.signature != cand.signature:
        reasons.append("baseline and candidate were measured on different task sets: re-run the baseline")
    if math.isnan(base.loss) or math.isnan(cand.loss):  # NaN compares False to everything: it must not pass
        reasons.append(f"loss missing: base={base.loss} candidate={cand.loss}")
    elif cand.loss > base.loss:
        reasons.append(f"loss regressed: {cand.loss:.4f} > {base.loss:.4f}")
    if cand.tool_validity < base.tool_validity - TOOL_TOLERANCE:
        reasons.append(f"tool validity regressed: {cand.tool_validity:.2f} < {base.tool_validity:.2f} - 0.05")
    if cand.task_pass < base.task_pass:
        reasons.append(f"task pass rate regressed: {cand.task_pass:.2f} < {base.task_pass:.2f}")
    return (not reasons, "; ".join(reasons) or "candidate passes the gate")


def chat_completion(base_url: str, messages: list[dict], tools: list[dict], timeout: float = 300.0) -> dict:
    payload = {
        "model": "local",
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 512,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _arguments_ok(raw) -> bool:
    if isinstance(raw, dict):
        return True
    try:
        return isinstance(json.loads(raw or ""), dict)
    except (json.JSONDecodeError, TypeError):
        return False


def tool_validity(
    base_url: str, requests_file: Path, tools: list[dict] | None = None
) -> tuple[float, list[dict]]:
    """Fraction of requests answered correctly: a valid native call to a known tool when one is expected,
    a plain answer when none is."""
    tools = tools or load_tools()
    names = {t["function"]["name"] for t in tools}
    requests = json.loads(requests_file.read_text(encoding="utf-8"))
    details = []
    for req in requests:
        messages = [{"role": "system", "content": EVAL_SYSTEM}, {"role": "user", "content": req["prompt"]}]
        try:
            message = chat_completion(base_url, messages, tools)["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            error = None
        except Exception as exc:
            calls, error = [], str(exc)
        called = [c.get("function", {}).get("name") for c in calls]
        if req.get("should_call_tool", True):
            valid = bool(calls) and all(
                c.get("function", {}).get("name") in names
                and _arguments_ok(c.get("function", {}).get("arguments"))
                for c in calls
            )
        else:
            valid = not calls and error is None
        details.append(
            {
                "id": req.get("id"),
                "prompt": req["prompt"],
                "expected_tool": req.get("expected_tool"),
                "called": called,
                "valid": valid,
                "error": error,
            }
        )
    score = round(sum(d["valid"] for d in details) / len(details), 4) if details else 0.0
    return score, details


def run_task_cli(task_path: Path, base_url: str, ctx_tokens: int) -> dict:
    """One task through the agent (Python 3.14 environment) against an already running server."""
    with tempfile.TemporaryDirectory(prefix="petru-eval-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "result.json"
        cmd = [
            "py", "-3.14", "-m", "uv", "run", "python", "-m", "petru.trajectory", str(task_path),
            "--base-url", base_url, "--out", str(out), "--tier", "default",
            "--project", str(Path(tmp) / "project"),
        ]  # fmt: skip
        subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8")
        if not out.exists():
            return {"name": task_path.stem, "passed": False, "seconds": 0.0, "stop_reason": "runner error"}
        data = json.loads(out.read_text(encoding="utf-8"))
        data["turns"] = len(data.pop("messages", []))  # the transcript itself is too large for the report
        data.pop("tools", None)
        data["check_output"] = str(data.get("check_output") or "")[-2000:]  # the tail says why a check failed
        return data


def task_pass(
    base_url: str,
    tasks_dir: Path,
    ctx_tokens: int,
    limit: int = TASK_LIMIT,
    runner: TaskRunner = run_task_cli,
) -> tuple[float, list[dict]]:
    tasks = select_eval_tasks(tasks_dir, limit)
    details = []
    for task in tasks:
        result = runner(task, base_url, ctx_tokens)
        details.append(
            {
                "name": result.get("name", task.stem),
                "passed": bool(result.get("passed")),
                "seconds": result.get("seconds"),
                "stop_reason": result.get("stop_reason"),
            }
        )
    rate = round(sum(d["passed"] for d in details) / len(details), 4) if details else 0.0
    return rate, details


ASSISTANT_START = "<|im_start|>assistant\n"
TURN_END = "<|im_end|>"


def assistant_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of every assistant reply, end marker included: exactly what training puts loss on."""
    spans = []
    start = text.find(ASSISTANT_START)
    while start != -1:
        body = start + len(ASSISTANT_START)
        end = text.find(TURN_END, body)
        end = len(text) if end == -1 else end + len(TURN_END)
        spans.append((body, end))
        start = text.find(ASSISTANT_START, end)
    return spans


def label_mask(offsets: list[tuple[int, int]], spans: list[tuple[int, int]]) -> list[bool]:
    """True for tokens whose characters lie inside an assistant span (zero-width tokens never count)."""
    return [a < b and any(lo <= a and b <= hi for lo, hi in spans) for a, b in offsets]


def held_out_loss(
    model_dir: Path, adapter_dir: Path | None, eval_file: Path, max_seq_len: int = 4096
) -> float:
    """Mean loss over the assistant tokens of the held-out transcripts (4-bit base plus optional adapter).
    Runs in a child process so the GPU is free again afterwards."""
    from petru_train.isolate import run_isolated

    return run_isolated(
        "petru_train.evaluate:assistant_loss_from_json",
        {
            "model_dir": str(model_dir),
            "adapter_dir": str(adapter_dir) if adapter_dir else None,
            "eval_file": str(eval_file),
            "max_seq_len": max_seq_len,
        },
    )


def assistant_loss_from_json(
    model_dir: str, adapter_dir: str | None, eval_file: str, max_seq_len: int
) -> float:
    return _assistant_loss(
        Path(model_dir), Path(adapter_dir) if adapter_dir else None, Path(eval_file), max_seq_len
    )


def _assistant_loss(model_dir: Path, adapter_dir: Path | None, eval_file: Path, max_seq_len: int) -> float:
    import torch
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        str(model_dir), max_seq_length=max_seq_len, load_in_4bit=True, dtype=None
    )
    tokenizer = text_tokenizer(tokenizer)
    if adapter_dir is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter_dir))
    FastLanguageModel.for_inference(model)
    total_loss, total_tokens = 0.0, 0
    with torch.no_grad():
        for sample in read_jsonl(eval_file):
            text = render_chat(sample, tokenizer)
            encoded = tokenizer(
                text,
                return_offsets_mapping=True,
                truncation=True,
                max_length=max_seq_len,
                add_special_tokens=False,
            )
            mask = label_mask([tuple(o) for o in encoded["offset_mapping"]], assistant_spans(text))
            if sum(mask) < 2:
                continue
            ids = torch.tensor([encoded["input_ids"]], device="cuda")
            labels = ids.clone()
            labels[0, [i for i, keep in enumerate(mask) if not keep]] = -100
            output = model(input_ids=ids, labels=labels)
            counted = sum(mask[1:])  # the model predicts token i from tokens < i, so position 0 never counts
            total_loss += float(output.loss) * counted
            total_tokens += counted
    return round(total_loss / total_tokens, 4) if total_tokens else float("nan")


def gate_inputs(base: EvalResult, cand: EvalResult, train_report: dict) -> tuple[EvalResult, EvalResult]:
    """Both losses come from the training run itself (base measured before step 0 on the same eval set and
    mask), so a rebuilt dataset never compares a new candidate with an old baseline loss."""
    return (
        replace(base, loss=float(train_report["base_eval_loss"])),
        replace(cand, loss=float(train_report["eval_loss"])),
    )


def evaluate(
    gguf: Path,
    tasks_dir: Path = TASKS_DIR,
    requests_file: Path = REQUESTS_FILE,
    port: int = 8081,
    ctx: int = 16384,
    limit: int = TASK_LIMIT,
    log: Path | None = None,
) -> EvalResult:
    """Tool validity and task pass rate of a GGUF served by llama-server; the loss comes from training."""
    loss = float("nan")
    proc = start_server(gguf, port, ctx, log=log)
    try:
        if not wait_healthy(port, proc=proc):
            raise RuntimeError(f"llama-server did not become healthy for {gguf}")
        base_url = f"http://127.0.0.1:{port}/v1"
        validity, validity_details = tool_validity(base_url, requests_file)
        passed, task_details = task_pass(base_url, tasks_dir, ctx, limit)
    finally:
        stop(proc)
    details = {"tool_validity": validity_details, "task_pass": task_details}
    return EvalResult(loss, validity, passed, details, tasks_signature(tasks_dir, requests_file, limit))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the base model or a run's candidate; write the gate."
    )
    parser.add_argument("--base", action="store_true", help="evaluate the base model into runs/baseline/")
    parser.add_argument(
        "--run", type=Path, default=None, help="run directory with adapter/, train_report.json and a gguf"
    )
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args(argv)
    if args.base:
        run_dir = TRAINING_DIR / "runs" / "baseline"
        result = evaluate(BASE_GGUF, limit=args.limit, port=args.port, log=run_dir / "server.log")
        result.save(run_dir / "eval_base.json")
        print(json.dumps({"tool_validity": result.tool_validity, "task_pass": result.task_pass}))
        return 0
    if args.run is None:
        parser.error("--base or --run is required")
    candidates = sorted(args.run.glob("candidate-Q*.gguf"))
    if not candidates:
        parser.error(f"no candidate gguf in {args.run}; run petru_train.export first")
    result = evaluate(candidates[0], limit=args.limit, port=args.port, log=args.run / "server.log")
    result.save(args.run / "eval_cand.json")
    report = json.loads((args.run / "train_report.json").read_text(encoding="utf-8"))
    base, result = gate_inputs(
        EvalResult.load(TRAINING_DIR / "runs" / "baseline" / "eval_base.json"), result, report
    )
    passed, why = gate(base, result)
    (args.run / "gate.json").write_text(
        json.dumps({"passed": passed, "reason": why}, indent=2), encoding="utf-8"
    )
    print(json.dumps({"passed": passed, "reason": why, "candidate": asdict(result) | {"details": "..."}}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
