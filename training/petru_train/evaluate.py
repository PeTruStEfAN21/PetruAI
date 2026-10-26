"""Three numbers per model and the gate comparing them: held-out loss, tool-call validity, task pass rate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from petru_train.samples import load_tools, read_jsonl, render_chat
from petru_train.server import start_server, stop, wait_healthy

TRAINING_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_DIR.parent
REQUESTS_FILE = TRAINING_DIR / "eval" / "tool_requests.json"
TASKS_DIR = TRAINING_DIR / "tasks"
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

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> EvalResult:
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def gate(base: EvalResult, cand: EvalResult) -> tuple[bool, str]:
    reasons = []
    if cand.loss > base.loss:
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
        data.pop("messages", None)
        data.pop("tools", None)
        return data


def task_pass(
    base_url: str, tasks_dir: Path, ctx_tokens: int, limit: int = 6, runner: TaskRunner = run_task_cli
) -> tuple[float, list[dict]]:
    tasks = sorted(tasks_dir.glob("*.toml"))[:limit]
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


def held_out_loss(
    model_dir: Path, adapter_dir: Path | None, eval_file: Path, max_seq_len: int = 4096
) -> float:
    """Mean token loss over the held-out transcripts (4-bit base plus optional adapter). Frees the GPU."""
    import torch
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        str(model_dir), max_seq_length=max_seq_len, load_in_4bit=True, dtype=None
    )
    if adapter_dir is not None:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(adapter_dir))
    FastLanguageModel.for_inference(model)
    losses = []
    with torch.no_grad():
        for sample in read_jsonl(eval_file):
            encoded = tokenizer(
                render_chat(sample, tokenizer), return_tensors="pt", truncation=True, max_length=max_seq_len
            ).to("cuda")
            output = model(input_ids=encoded.input_ids, labels=encoded.input_ids)
            losses.append(float(output.loss))
    del model
    torch.cuda.empty_cache()
    return round(sum(losses) / len(losses), 4) if losses else float("nan")


def evaluate(
    model_dir: Path,
    adapter_dir: Path | None,
    gguf: Path,
    eval_file: Path,
    tasks_dir: Path = TASKS_DIR,
    requests_file: Path = REQUESTS_FILE,
    port: int = 8081,
    ctx: int = 16384,
    limit: int = 6,
    max_seq_len: int = 4096,
    log: Path | None = None,
) -> EvalResult:
    loss = held_out_loss(model_dir, adapter_dir, eval_file, max_seq_len)
    proc = start_server(gguf, port, ctx, log=log)
    try:
        if not wait_healthy(port, proc=proc):
            raise RuntimeError(f"llama-server did not become healthy for {gguf}")
        base_url = f"http://127.0.0.1:{port}/v1"
        validity, validity_details = tool_validity(base_url, requests_file)
        passed, task_details = task_pass(base_url, tasks_dir, ctx, limit)
    finally:
        stop(proc)
    return EvalResult(loss, validity, passed, {"tool_validity": validity_details, "task_pass": task_details})


def main(argv: list[str] | None = None) -> int:
    from petru_train.env import MODEL_DIR

    parser = argparse.ArgumentParser(
        description="Evaluate the base model or a run's candidate; write the gate."
    )
    parser.add_argument("--base", action="store_true", help="evaluate the base model into runs/baseline/")
    parser.add_argument(
        "--run", type=Path, default=None, help="run directory with adapter/ and candidate gguf"
    )
    parser.add_argument("--eval-file", type=Path, default=TRAINING_DIR / "data" / "eval.jsonl")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--max-seq-len", type=int, default=4096)
    args = parser.parse_args(argv)
    if args.base:
        run_dir = TRAINING_DIR / "runs" / "baseline"
        result = evaluate(MODEL_DIR, None, BASE_GGUF, args.eval_file, limit=args.limit, port=args.port,
                          max_seq_len=args.max_seq_len, log=run_dir / "server.log")  # fmt: skip
        result.save(run_dir / "eval_base.json")
        print(
            json.dumps(
                {"loss": result.loss, "tool_validity": result.tool_validity, "task_pass": result.task_pass}
            )
        )
        return 0
    if args.run is None:
        parser.error("--base or --run is required")
    candidates = sorted(args.run.glob("*.gguf"))
    if not candidates:
        parser.error(f"no candidate gguf in {args.run}; run petru_train.export first")
    result = evaluate(MODEL_DIR, args.run / "adapter", candidates[0], args.eval_file, limit=args.limit,
                      port=args.port, max_seq_len=args.max_seq_len, log=args.run / "server.log")  # fmt: skip
    result.save(args.run / "eval_cand.json")
    base = EvalResult.load(TRAINING_DIR / "runs" / "baseline" / "eval_base.json")
    passed, why = gate(base, result)
    (args.run / "gate.json").write_text(
        json.dumps({"passed": passed, "reason": why}, indent=2), encoding="utf-8"
    )
    print(json.dumps({"passed": passed, "reason": why, "candidate": asdict(result) | {"details": "..."}}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
