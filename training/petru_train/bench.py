"""The team (the 35B leading a faster assistant) against the 35B alone: same tasks, same rules.

Both servers stay loaded for both modes, so the only difference is whether the lead may delegate. Each task
runs in both modes, in alternating order (a warm cache never favours one mode), and the report is saved after
every run, so a stopped comparison resumes.

    py -3.14 -m uv run python -m petru_train.bench --tasks bench,heldout --per-language 2

A probe asks the lead only whether it would work as a team, a few times per task, in minutes instead of hours:

    py -3.14 -m uv run python -m petru_train.bench --tasks python_tracker --probe 3
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from petru_train.evaluate import BASE_GGUF, held_out_tasks
from petru_train.exercism import TASKS_DIR as EXERCISM_TASKS
from petru_train.export import MODELS_DIR, TUNED_FILE
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
BUILD_OUTPUT = ("bin", "obj", "target", "build", "node_modules", ".gradle", ".dart_tool", "__pycache__")
BUILD_OUTPUT += (".git",)  # the agent's own history; the sources are what is kept
Runner = Callable[[Path, str], dict]


def delegations(messages: list[dict]) -> int:
    return sum(
        1
        for message in messages
        for call in message.get("tool_calls") or []
        if call.get("function", {}).get("name") == "delegate"
    )


def read_result(out: Path, keep: Path | None = None) -> dict:
    """The row of one finished attempt; its full transcript is copied to `keep` for later reading."""
    data = json.loads(out.read_text(encoding="utf-8"))
    if keep is not None:
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, keep)
    return {
        "passed": bool(data.get("passed")),
        "seconds": data.get("seconds"),
        "tokens": data.get("tokens"),
        "stop_reason": data.get("stop_reason"),
        "delegations": data.get("delegations", delegations(data.get("messages") or [])),
        "team_choice": data.get("team_choice"),
        "team_reason": data.get("team_reason"),
    }


def assistant_gguf(models_dir: Path = MODELS_DIR) -> Path:
    """The team's assistant: the promoted fine-tune once there is one, else the base 4B."""
    tuned = models_dir / TUNED_FILE
    return tuned if tuned.is_file() else BASE_GGUF


def keep_project(project: Path, dest: Path) -> None:
    """The sources a run wrote, without what the build regenerates, for reading (and showing) later."""
    if project.is_dir():
        shutil.copytree(project, dest, ignore=shutil.ignore_patterns(*BUILD_OUTPUT), dirs_exist_ok=True)


def attempt_timeout(task: Path) -> float:
    """Seconds an attempt at `task` may take: ATTEMPT_TIMEOUT_S, or the task's own bench_minutes when it is
    large enough to need more."""
    try:
        minutes = tomllib.loads(task.read_text(encoding="utf-8")).get("bench_minutes")
    except (OSError, tomllib.TOMLDecodeError):
        minutes = None
    return float(minutes * 60) if isinstance(minutes, int | float) else float(ATTEMPT_TIMEOUT_S)


def own_time_limit(limit: float) -> float:
    """When an attempt with `limit` seconds stops itself: early enough for a last long reply to finish and its
    transcript to be saved (10%, at most 15 minutes); the kill at `limit` stays a backstop."""
    return limit - min(900.0, limit / 10)


def run_mode(
    task: Path,
    mode: str,
    lead_url: str,
    worker_url: str,
    keep: Path | None = None,
    assistant: str | None = None,
) -> dict:
    """One attempt through petru.trajectory (agent env); past the timeout, its tree is killed. A team row
    names its `assistant` model, so a report resumed after a promotion shows which runs had which."""
    row = _attempt(task, mode, lead_url, worker_url, keep)
    return {**row, "assistant": assistant} if mode == "team" and assistant else row


def _attempt(task: Path, mode: str, lead_url: str, worker_url: str, keep: Path | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="petru-bench-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "result.json"
        cmd = [
            "py", "-3.14", "-m", "uv", "run", "python", "-m", "petru.trajectory", str(task),
            "--tier", "quality", "--base-url", lead_url, "--out", str(out),
            "--project", str(Path(tmp) / "project"),
        ]  # fmt: skip
        limit = attempt_timeout(task)
        cmd += ["--time-limit", str(own_time_limit(limit))]
        if mode in ("team", "choice"):
            cmd += ["--team", "--worker-tier", "fast", "--worker-base-url", worker_url]
        if mode == "choice":
            cmd += ["--choice-only"]
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        timed_out = False
        try:
            proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            kill_tree(proc.pid)
            timed_out = True
        if keep is not None:
            keep_project(Path(tmp) / "project", keep.with_suffix(""))
        if timed_out:
            return {"passed": False, "seconds": limit, "stop_reason": "timeout"}
        if not out.is_file():
            return {"passed": False, "seconds": None, "stop_reason": "runner error"}
        return read_result(out, keep)


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


def probe(tasks: list[Path], runner: Runner, runs: int, report_file: Path) -> dict:
    """The lead's choice of team or solo, `runs` times per task, with its reasons; resumable."""
    results = []
    if report_file.is_file():
        results = json.loads(report_file.read_text(encoding="utf-8")).get("results", [])
    for task in tasks:
        name = task_name(task)
        for _ in range(runs - sum(r["task"] == name for r in results)):
            row = {"task": name, "mode": "choice", **runner(task, "choice")}
            results.append(row)
            print(f"{name}: {row.get('team_choice')} ({row.get('team_reason')})", flush=True)
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report = {"results": results, "summary": _choices(results)}
            report_file.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return {"results": results, "summary": _choices(results)}


def _choices(results: list[dict]) -> dict:
    summary: dict[str, dict[str, int]] = {}
    for row in results:
        counts = summary.setdefault(row["task"], {})
        choice = row.get("team_choice") or "none"
        counts[choice] = counts.get(choice, 0) + 1
    return summary


def bench_tasks(kinds: list[str], per_language: int) -> list[Path]:
    tasks: list[Path] = []
    if "bench" in kinds:
        tasks += sorted(BENCH_DIR.glob("*/task.toml"))
    if "heldout" in kinds:
        tasks += held_out_tasks(EXERCISM_TASKS, per_language=per_language)
    for name in (k for k in kinds if k not in ("bench", "heldout")):  # one bench project, by name
        task = BENCH_DIR / name / "task.toml"
        if not task.is_file():
            raise SystemExit(f"no bench project {name!r} in {BENCH_DIR}")
        tasks.append(task)
    return tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The team against the 35B alone, on the same tasks.")
    parser.add_argument(
        "--tasks",
        default="bench,heldout",
        help="bench (multi-file projects), heldout (Exercism) or a bench project's name",
    )
    parser.add_argument("--per-language", type=int, default=2, help="held-out Exercism tasks per language")
    parser.add_argument("--report", type=Path, default=None, help="resume this report")
    parser.add_argument(
        "--probe", type=int, default=0, help="only ask the lead this many times per task: team or solo"
    )
    args = parser.parse_args(argv)
    tasks = bench_tasks([k.strip() for k in args.tasks.split(",")], args.per_language)
    report = args.report or REPORTS_DIR / f"{datetime.now():%Y-%m-%d-%H%M}.json"
    lead = start_server(
        TEACHER_GGUF, LEAD_PORT, LEAD_CTX, log=report.with_suffix(".lead.log"), extra=("--cpu-moe",)
    )
    assistant = assistant_gguf()
    print(f"assistant: {assistant.name}", flush=True)
    worker = None  # a probe ends before anything is delegated: no assistant to load
    if not args.probe:
        worker = start_server(assistant, WORKER_PORT, WORKER_CTX, log=report.with_suffix(".worker.log"))
    try:
        lead_up = wait_healthy(LEAD_PORT, timeout_s=900, proc=lead)
        if not (lead_up and (worker is None or wait_healthy(WORKER_PORT, proc=worker))):
            raise RuntimeError("a model server did not start; see the logs next to the report")
        lead_url, worker_url = f"http://127.0.0.1:{LEAD_PORT}/v1", f"http://127.0.0.1:{WORKER_PORT}/v1"
        transcripts = report.with_suffix("")  # one <task>-<mode>.json per attempt, next to the report

        def runner(task: Path, mode: str) -> dict:
            keep = transcripts / f"{task_name(task)}-{mode}.json"
            if mode == "choice":  # a probe asks several times: one transcript each
                keep = keep.with_stem(f"{keep.stem}-{len(list(transcripts.glob(f'{keep.stem}-*.json'))) + 1}")
            return run_mode(task, mode, lead_url, worker_url, keep, assistant.name)

        result = probe(tasks, runner, args.probe, report) if args.probe else compare(tasks, runner, report)
    finally:
        stop(lead)
        if worker is not None:
            stop(worker)
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
