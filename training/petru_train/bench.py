"""The team (the 35B leading a faster assistant) against the 35B alone: same tasks, same rules.

Both servers stay loaded for both modes, so the only difference is whether the lead may delegate. Each task
runs in both modes, in alternating order (a warm cache never favours one mode), and the report is saved after
every run, so a stopped comparison resumes.

    py -3.14 -m uv run python -m petru_train.bench --tasks bench,heldout --per-language 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from petru_train.evaluate import BASE_GGUF, held_out_tasks
from petru_train.exercism import TASKS_DIR as EXERCISM_TASKS
from petru_train.server import start_server, stop, wait_healthy
from petru_train.teacher import TEACHER_GGUF
from petru_train.trajectories import REPO_ROOT, kill_tree, task_name

TRAINING_DIR = Path(__file__).resolve().parents[1]
BENCH_DIR = TRAINING_DIR / "bench"
REPORTS_DIR = TRAINING_DIR / "runs" / "bench"
LEAD_PORT, WORKER_PORT = 8082, 8092
LEAD_CTX, WORKER_CTX = 32768, 32768  # the quality and fast tiers' contexts
ATTEMPT_TIMEOUT_S = 3600
MODES = ("solo", "team")
Runner = Callable[[Path, str], dict]


def delegations(messages: list[dict]) -> int:
    return sum(
        1
        for message in messages
        for call in message.get("tool_calls") or []
        if call.get("function", {}).get("name") == "delegate"
    )


def run_mode(task: Path, mode: str, lead_url: str, worker_url: str) -> dict:
    """One attempt through petru.trajectory (agent env); past the timeout, its tree is killed."""
    with tempfile.TemporaryDirectory(prefix="petru-bench-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "result.json"
        cmd = [
            "py", "-3.14", "-m", "uv", "run", "python", "-m", "petru.trajectory", str(task),
            "--tier", "quality", "--base-url", lead_url, "--out", str(out),
            "--project", str(Path(tmp) / "project"),
        ]  # fmt: skip
        if mode == "team":
            cmd += ["--team", "--worker-tier", "fast", "--worker-base-url", worker_url]
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=ATTEMPT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            kill_tree(proc.pid)
            return {"passed": False, "seconds": float(ATTEMPT_TIMEOUT_S), "stop_reason": "timeout"}
        if not out.is_file():
            return {"passed": False, "seconds": None, "stop_reason": "runner error"}
        data = json.loads(out.read_text(encoding="utf-8"))
        return {
            "passed": bool(data.get("passed")),
            "seconds": data.get("seconds"),
            "tokens": data.get("tokens"),
            "stop_reason": data.get("stop_reason"),
            "delegations": delegations(data.get("messages") or []),
        }


def _summary(results: list[dict]) -> dict:
    summary = {}
    for mode in MODES:
        rows = [r for r in results if r["mode"] == mode]
        seconds = [r["seconds"] for r in rows if isinstance(r.get("seconds"), int | float)]
        summary[mode] = {
            "passed": sum(bool(r["passed"]) for r in rows),
            "tasks": len(rows),
            "pass_rate": round(sum(bool(r["passed"]) for r in rows) / len(rows), 4) if rows else 0.0,
            "mean_seconds": round(sum(seconds) / len(seconds), 1) if seconds else None,
        }
    return summary


def compare(tasks: list[Path], runner: Runner, report_file: Path) -> dict:
    """Every task solo and as a team, alternating which goes first; resumable from `report_file`."""
    results = []
    if report_file.is_file():
        results = json.loads(report_file.read_text(encoding="utf-8")).get("results", [])
    done = {(r["task"], r["mode"]) for r in results}
    for index, task in enumerate(tasks):
        name = task_name(task)
        for mode in MODES if index % 2 == 0 else tuple(reversed(MODES)):
            if (name, mode) in done:
                continue
            row = {"task": name, "mode": mode, **runner(task, mode)}
            results.append(row)
            print(f"{name} {mode}: {'PASS' if row['passed'] else 'FAIL'} {row.get('seconds')}s", flush=True)
            report = {"results": results, "summary": _summary(results)}
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return {"results": results, "summary": _summary(results)}


def bench_tasks(kinds: list[str], per_language: int) -> list[Path]:
    tasks: list[Path] = []
    if "bench" in kinds:
        tasks += sorted(BENCH_DIR.glob("*/task.toml"))
    if "heldout" in kinds:
        tasks += held_out_tasks(EXERCISM_TASKS, per_language=per_language)
    return tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The team against the 35B alone, on the same tasks.")
    parser.add_argument(
        "--tasks", default="bench,heldout", help="bench (multi-file projects), heldout (Exercism)"
    )
    parser.add_argument("--per-language", type=int, default=2, help="held-out Exercism tasks per language")
    parser.add_argument("--report", type=Path, default=None, help="resume this report")
    args = parser.parse_args(argv)
    tasks = bench_tasks([k.strip() for k in args.tasks.split(",")], args.per_language)
    report = args.report or REPORTS_DIR / f"{datetime.now():%Y-%m-%d-%H%M}.json"
    lead = start_server(
        TEACHER_GGUF, LEAD_PORT, LEAD_CTX, log=report.with_suffix(".lead.log"), extra=("--cpu-moe",)
    )
    worker = start_server(BASE_GGUF, WORKER_PORT, WORKER_CTX, log=report.with_suffix(".worker.log"))
    try:
        if not (wait_healthy(LEAD_PORT, timeout_s=900, proc=lead) and wait_healthy(WORKER_PORT, proc=worker)):
            raise RuntimeError("a model server did not start; see the logs next to the report")
        lead_url, worker_url = f"http://127.0.0.1:{LEAD_PORT}/v1", f"http://127.0.0.1:{WORKER_PORT}/v1"
        result = compare(tasks, lambda task, mode: run_mode(task, mode, lead_url, worker_url), report)
    finally:
        stop(lead)
        stop(worker)
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
