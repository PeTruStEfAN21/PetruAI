"""Verified trajectories: run the harness tasks with the local model and keep only what passed the checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from petru_train.samples import Sample

TRAINING_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_DIR.parent
DEFAULT_CONFIG = TRAINING_DIR / "config" / "trajectories.toml"
LANGUAGE_BY_PREFIX = {
    "python": "python",
    "py": "python",
    "ts": "typescript",
    "js": "javascript",
    "flutter": "dart",
    "dart": "dart",
    "go": "go",
    "rust": "rust",
    "c": "c",
    "cpp": "cpp",
    "csharp": "csharp",
    "java": "java",
    "kotlin": "kotlin",
    "ruby": "ruby",
    "php": "php",
    "r": "r",
    "shell": "shell",
    "sql": "sql",
    "swift": "swift",
    "scala": "scala",
}
Runner = Callable[[Path, "TrajConfig", int], dict]


@dataclass
class TrajConfig:
    tasks_dir: Path
    out: Path
    tier: str = "quality"
    samples_per_task: int = 3
    attempts_per_task: int = 4
    max_tokens: int = 0  # 0 = no limit: every verified example is kept, however long
    base_url: str | None = None
    attempt_timeout_s: int = 900
    max_minutes: int | None = None
    state_file: Path | None = None  # progress per task; the night keeps one per run so each night generates
    parallel: int = 1  # attempts at once on one server: one generates while another runs its tests


def task_name(task_path: Path) -> str:
    """The task's own name: seeded tasks all live in `<name>/task.toml`."""
    if not task_path.is_file():
        return task_path.stem
    data = tomllib.loads(task_path.read_text(encoding="utf-8"))
    return str(data.get("name") or task_path.stem)


def load_traj_config(path: Path = DEFAULT_CONFIG, base_dir: Path | None = None) -> TrajConfig:
    base = base_dir or path.parent.parent
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return TrajConfig(
        tasks_dir=base / data.get("tasks_dir", "tasks"),
        out=base / data.get("out", "data/trajectories.jsonl"),
        tier=str(data.get("tier", "quality")),
        samples_per_task=int(data.get("samples_per_task", 3)),
        attempts_per_task=int(data.get("attempts_per_task", 4)),
        max_tokens=int(data.get("max_tokens", 0)),
        base_url=data.get("base_url"),
        attempt_timeout_s=int(data.get("attempt_timeout_s", 900)),
        max_minutes=data.get("max_minutes"),
    )


def language_for(task_name: str) -> str:
    return LANGUAGE_BY_PREFIX.get(task_name.split("_")[0].lower(), "unknown")


# What petru.trajectory sends when the model misbehaves (kept in sync with petru/trajectory.py).
DESIGN_HINT = " (Use the ask_user tool for further questions, then call plan.)"
CONTINUE_PREFIX = "Continue with the confirmed plan using tools."
# What the agent answers a looping ask_user with (kept in sync with petru/tools/interaction.py).
QUESTION_GUARDS = ("You already asked this question.", "That is enough design questions")
INVALID_CALL = "Invalid tool call:"  # petru/agent/loop.py, Agent._invalid
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")  # terminal color codes (petru/tools/shell.py, _ANSI_RE)


def normalize_messages(messages: list[dict]) -> list[dict]:
    """Rewrite the harness's corrections into the behaviour the agent should learn. A design question the
    model wrote as plain text, answered by the scripted user, becomes an ask_user call whose result is the
    answer; a BUILD-phase stop followed by the harness's 'continue' is dropped, and so is a question the
    agent turned away as repeated or excess, and a single call the agent rejected as invalid. Idempotent."""
    out: list[dict] = []
    i, asked = 0, 0
    while i < len(messages):
        message = messages[i]
        following = messages[i + 1] if i + 1 < len(messages) else {}
        reply = str(following.get("content") or "")
        is_text_turn = message.get("role") == "assistant" and not message.get("tool_calls")
        if is_text_turn and following.get("role") == "user":
            question = str(message.get("content") or "").strip()
            if reply.endswith(DESIGN_HINT) and question:
                asked += 1
                call_id = f"call_ask_text_{asked}"
                arguments = json.dumps({"question": question}, ensure_ascii=False)
                call = {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "ask_user", "arguments": arguments},
                }
                out.append({"role": "assistant", "content": "", "tool_calls": [call]})
                out.append({"role": "tool", "tool_call_id": call_id, "content": reply[: -len(DESIGN_HINT)]})
                i += 2
                continue
            if reply.startswith(CONTINUE_PREFIX):
                i += 2
                continue
        calls = message.get("tool_calls") or []
        guarded = reply.startswith(QUESTION_GUARDS) and following.get("role") == "tool"
        if len(calls) == 1 and calls[0]["function"]["name"] == "ask_user" and guarded:
            i += 2  # a repeated or excess question: the model should have called plan instead
            continue
        if len(calls) == 1 and following.get("role") == "tool" and reply.startswith(INVALID_CALL):
            i += 2  # a malformed call; the corrected one that follows is what the model should learn
            continue
        if message.get("role") == "tool" and ANSI_RE.search(str(message.get("content") or "")):
            message = {**message, "content": ANSI_RE.sub("", message["content"])}  # the agent strips them now
        out.append(message)
        i += 1
    return out


PLAN_CONFIRMED = "Plan confirmed"  # petru/tools/interaction.py, PlanTool
# The sections the agent appends to its system prompt (petru/agent/context.py), in order; the first two exist
# only once a plan is confirmed, so the DESIGN-phase prompt never had them.
PROMPT_SECTIONS = (
    "## Confirmed plan: ",
    "## Project instructions (AGENTS.md)",
    "## DECISIONS (final; the latest entry wins)",
    "## Memory (global)",
    "## Memory (project)",
    "## Recent commits (journal)",
    "Environment: no internet",
)
BUILD_ONLY_SECTIONS = PROMPT_SECTIONS[0], PROMPT_SECTIONS[2]


def design_system_prompt(final: str, build_prompt: str, design_prompt: str) -> str | None:
    """The system prompt the agent had during DESIGN, rebuilt from the one a transcript ends with (BUILD):
    the phase text swapped and the plan and decisions sections removed. None for an unknown prompt."""
    if not final.startswith(build_prompt):
        return None
    rest = final[len(build_prompt) :]
    starts = sorted(i for i in (rest.find(f"\n\n{header}") for header in PROMPT_SECTIONS) if i != -1)
    kept = rest[: starts[0]] if starts else rest
    for start, end in zip(starts, [*starts[1:], len(rest)], strict=True):
        if not rest[start + 2 : end].startswith(BUILD_ONLY_SECTIONS):
            kept += rest[start:end]
    return design_prompt + kept


def _plan_section(message: dict) -> str | None:
    """The '## Confirmed plan' section of the agent's BUILD prompt (petru/agent/context.py, render_plan),
    rebuilt from the plan call."""
    for call in message.get("tool_calls") or []:
        if call.get("function", {}).get("name") != "plan":
            continue
        try:
            args = json.loads(call["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            return None
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(args.get("steps") or [], start=1))
        return f"{PROMPT_SECTIONS[0]}{args.get('title', '')}\n{steps}"
    return None


def split_by_phase(sample: Sample, build_prompt: str, design_prompt: str) -> list[Sample]:
    """A trajectory as two samples, each under the system prompt the agent really had: DESIGN (questions and
    the plan, up to its confirmation) and BUILD (the request, then the work). A transcript keeps only its last
    prompt (BUILD), which would otherwise teach questions under the BUILD prompt. Anything else stays
    whole."""
    messages = sample.messages
    if sample.source != "trajectory" or len(messages) < 2 or messages[0].get("role") != "system":
        return [sample]
    confirmed = next(
        (
            i
            for i, m in enumerate(messages)
            if m.get("role") == "tool" and str(m.get("content") or "").startswith(PLAN_CONFIRMED)
        ),
        None,
    )
    if (
        confirmed is None
        or confirmed + 1 >= len(messages)
        or messages[confirmed + 1].get("role") != "assistant"
    ):
        return [sample]
    design_system = design_system_prompt(str(messages[0].get("content") or ""), build_prompt, design_prompt)
    if design_system is None or messages[1].get("role") != "user":
        return [sample]
    design = [{"role": "system", "content": design_system}, *messages[1 : confirmed + 1]]
    build_system = str(messages[0].get("content") or "")
    plan = _plan_section(messages[confirmed - 1])
    if plan and PROMPT_SECTIONS[0] not in build_system:  # captured after task_complete cleared the plan
        build_system = f"{build_prompt}\n\n{plan}{build_system[len(build_prompt) :]}"
    build = [{"role": "system", "content": build_system}, messages[1], *messages[confirmed + 1 :]]
    return [
        replace(sample, id=f"{sample.id}#design", messages=design),
        replace(sample, id=f"{sample.id}#build", messages=build),
    ]


def rejection_reason(result: dict, max_tokens: int) -> str:
    """Why `result_to_sample` would drop this attempt, in one line; "" when it would be kept."""
    if result.get("stop_reason"):
        return f"stopped: {result['stop_reason']}"
    if not result.get("passed"):
        failed = [
            line for line in str(result.get("check_output") or "").splitlines() if line.startswith("[FAIL]")
        ]
        return f"checks failed: {failed[0]}" if failed else "checks failed"
    tokens = int(result.get("tokens") or 0)
    if max_tokens and tokens > max_tokens:
        return f"too long: {tokens} tokens"
    return ""


def result_to_sample(result: dict, task_name: str, max_tokens: int) -> Sample | None:
    """None unless the checks passed, the turn ended normally and the transcript fits max_tokens (0: any)."""
    if rejection_reason(result, max_tokens):
        return None
    # The recorded system prompt stays: it is what the agent sees at run time (rules, phase, packages).
    messages = normalize_messages(list(result.get("messages", [])))
    if not any(m.get("role") == "assistant" for m in messages):
        return None
    digest = hashlib.sha1(json.dumps(messages, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    return Sample(
        id=f"traj:{task_name}:{digest}",
        source="trajectory",
        repo=task_name,
        license="local-model",
        commit="",
        language=language_for(task_name),
        messages=messages,
        tools=list(result.get("tools") or []),
    )


def kill_tree(pid: int) -> None:
    """Kill a process and everything it started (uv -> python -> llama-server, npm, flutter)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        subprocess.run(["pkill", "-TERM", "-P", str(pid)], capture_output=True)  # children first
        subprocess.run(["kill", "-TERM", str(pid)], capture_output=True)


def run_petru_task(task_path: Path, cfg: TrajConfig, attempt: int) -> dict:
    """One attempt through `python -m petru.trajectory` in the agent's environment, in a temporary project.
    A run past `attempt_timeout_s` is killed with its whole process tree and counts as failed."""
    with tempfile.TemporaryDirectory(prefix="petru-traj-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "result.json"
        log = Path(tmp) / "runner.log"
        cmd = [
            "py", "-3.14", "-m", "uv", "run", "python", "-m", "petru.trajectory", str(task_path),
            "--out", str(out), "--tier", cfg.tier, "--project", str(Path(tmp) / "project"),
        ]  # fmt: skip
        if cfg.base_url:
            cmd += ["--base-url", cfg.base_url]
        with log.open("w", encoding="utf-8") as sink:
            proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=sink, stderr=subprocess.STDOUT)
            try:
                proc.wait(timeout=cfg.attempt_timeout_s)
            except subprocess.TimeoutExpired:
                kill_tree(proc.pid)
                return {
                    "name": task_name(task_path),
                    "passed": False,
                    "stop_reason": f"timeout after {cfg.attempt_timeout_s}s",
                }
        if not out.exists():
            tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-5:]
            return {
                "name": task_name(task_path),
                "passed": False,
                "stop_reason": "runner error: " + " | ".join(tail),
            }
        return json.loads(out.read_text(encoding="utf-8"))


def _save_rejected(cfg: TrajConfig, name: str, attempt: int, result: dict) -> None:
    """The full transcript of a rejected attempt, next to the output, so a failing stack can be diagnosed."""
    folder = cfg.out.parent / "rejected"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}-{attempt}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _append_jsonl(path: Path, sample: Sample) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")


def _state_path(cfg: TrajConfig) -> Path:
    return cfg.state_file or cfg.out.with_name(cfg.out.name + ".state.json")


def _load_state(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"kept": {}, "attempts": {}}


def generate(
    cfg: TrajConfig,
    runner: Runner = run_petru_task,
    clock: Callable[[], float] = time.monotonic,
    tasks: list[Path] | None = None,
) -> dict:
    """Round-robin over the tasks (`tasks`, else the TOML files of `tasks_dir`), one attempt each per round,
    until every task has `samples_per_task` kept or `attempts_per_task` spent, or `max_minutes` is used up (no
    stack is starved). `parallel` attempts run at once, never two of the same task. Resumable."""
    tasks = list(tasks) if tasks is not None else sorted(cfg.tasks_dir.glob("*.toml"))
    names = {task: task_name(task) for task in tasks}
    state_path = _state_path(cfg)
    state = _load_state(state_path)
    for name in names.values():
        state["kept"].setdefault(name, 0)
        state["attempts"].setdefault(name, 0)
    started = clock()
    lock = threading.Lock()
    in_flight: set[str] = set()

    def out_of_time() -> bool:
        return cfg.max_minutes is not None and (clock() - started) / 60 >= cfg.max_minutes

    def save() -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")

    def next_task() -> Path | None:
        """The open task with the fewest attempts, in list order: one attempt each per round."""
        open_tasks = [
            (int(state["attempts"][name]), index, task)
            for index, (task, name) in enumerate(names.items())
            if name not in in_flight
            and int(state["kept"][name]) < cfg.samples_per_task
            and int(state["attempts"][name]) < cfg.attempts_per_task
        ]
        return min(open_tasks)[2] if open_tasks else None

    def worker() -> None:
        while True:
            with lock:
                task = None if out_of_time() else next_task()
                if task is None:
                    return
                name = names[task]
                in_flight.add(name)
                state["attempts"][name] = attempt = int(state["attempts"][name]) + 1
            try:
                result = runner(task, cfg, attempt)
            except Exception as exc:  # one broken attempt must not end the generation
                result = {"name": name, "passed": False, "stop_reason": f"runner error: {exc}"}
            sample = result_to_sample(result, name, cfg.max_tokens)
            with lock:
                in_flight.discard(name)
                if sample is not None:
                    _append_jsonl(cfg.out, sample)
                    state["kept"][name] = int(state["kept"][name]) + 1
                else:
                    _save_rejected(cfg, name, attempt, result)
                verdict = "kept" if sample else "rejected"
                line = f"{name} attempt {attempt}: {verdict} ({state['kept'][name]}/{cfg.samples_per_task})"
                reason = rejection_reason(result, cfg.max_tokens) if sample is None else ""
                print(f"{line}: {reason}" if reason else line, flush=True)
                save()

    workers = [threading.Thread(target=worker) for _ in range(max(1, cfg.parallel))]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()
    save()
    return {"tasks": len(tasks), "kept": dict(state["kept"]), "attempts": dict(state["attempts"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate verified agent trajectories for training.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--tier", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument(
        "--tasks", type=Path, default=None, help="a task file or directory (default from config)"
    )
    args = parser.parse_args(argv)
    cfg = load_traj_config(args.config)
    if args.tier:
        cfg.tier = args.tier
    if args.base_url:
        cfg.base_url = args.base_url
    if args.tasks is not None:
        cfg.tasks_dir = args.tasks if args.tasks.is_dir() else args.tasks.parent
        if args.tasks.is_file():
            cfg = TrajConfig(**{**asdict(cfg), "tasks_dir": args.tasks.parent})
            tasks_filter = {args.tasks.stem}
        else:
            tasks_filter = None
    else:
        tasks_filter = None
    if tasks_filter:
        original = cfg.tasks_dir
        with tempfile.TemporaryDirectory(prefix="petru-tasks-") as tmp:
            for name in tasks_filter:
                (Path(tmp) / f"{name}.toml").write_bytes((original / f"{name}.toml").read_bytes())
            cfg.tasks_dir = Path(tmp)
            stats = generate(cfg)
    else:
        stats = generate(cfg)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
