"""Train, export, evaluate and promote the language specialists, as many as the night allows.

Each specialist is a QLoRA fine-tune of the base model on its share of the dataset (petru_train.specialists),
exported to GGUF and promoted to infra/llama.cpp/models/specialists/<name>.gguf only when it does not regress
against the base model on its own gate. Every stage leaves a marker, so an interrupted night resumes.

    py -3.14 -m uv run python -m petru_train.specialist_night --run 2026-10-27 --until 2026-10-27T11:00
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from petru_train.evaluate import BASE_GGUF, TASKS_DIR, EvalResult, evaluate, gate, gate_inputs
from petru_train.export import MODELS_DIR, candidate_file, export_run
from petru_train.specialists import Specialist, load_specialists, write_specialist_data
from petru_train.train import TrainReport, load_train_config, train

TRAINING_DIR = Path(__file__).resolve().parents[1]
RUNS_DIR = TRAINING_DIR / "runs"
DATA_DIR = TRAINING_DIR / "data"
STATE_FILE = RUNS_DIR / "specialists.json"  # rotation: specialist -> the last run that trained it
MIN_TRAIN = 40  # fewer samples cannot teach a specialist anything reliable
MIN_TRAIN_MINUTES = 30
RESERVE_MIN = 90  # export, and the base and candidate evaluations on its tasks
MAX_TRAIN_MIN = 120  # training time per specialist and night, so the rotation reaches several of them


def rotation(specialists: list[Specialist], state: dict[str, str]) -> list[Specialist]:
    """Never-trained specialists first (in config order), then the one trained longest ago."""
    return sorted(specialists, key=lambda s: (s.name in state, state.get(s.name, "")))


def specialist_tasks(specialist: Specialist, tasks_dir: Path = TASKS_DIR) -> list[Path]:
    return sorted(t for t in tasks_dir.glob("*.toml") if t.stem.split("_")[0] in specialist.tasks)


def _write(path: Path, data: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def _base_result(tasks: list[Path], baseline_dir: Path, eval_fn: Callable) -> EvalResult:
    """The base model on these tasks, measured once and kept per task set (the file name is its signature)."""
    key = "-".join(t.stem for t in tasks) or "no-tasks"
    cached = baseline_dir / "specialists" / f"{key}.json"
    if cached.is_file():
        return EvalResult.load(cached)
    result = eval_fn(BASE_GGUF, tasks=tasks, log=baseline_dir / "specialists" / f"{key}.log")
    cached.parent.mkdir(parents=True, exist_ok=True)
    result.save(cached)
    return result


def run_one(
    specialist: Specialist,
    run_dir: Path,
    remaining_min: float,
    *,
    train_file: Path = DATA_DIR / "train.jsonl",
    eval_file: Path = DATA_DIR / "eval.jsonl",
    models_dir: Path = MODELS_DIR,
    baseline_dir: Path = RUNS_DIR / "baseline",
    tasks_dir: Path = TASKS_DIR,
    train_fn: Callable = train,
    export_fn: Callable = export_run,
    eval_fn: Callable = evaluate,
) -> dict:
    out = run_dir / "specialists" / specialist.name
    done = out / "done.json"
    if done.is_file():
        return json.loads(done.read_text(encoding="utf-8"))
    report_file = out / "train_report.json"
    if not report_file.is_file() and remaining_min < RESERVE_MIN + MIN_TRAIN_MINUTES:
        return {"status": "no time", "name": specialist.name}
    counts = write_specialist_data(train_file, eval_file, specialist, out / "data")
    if counts["train"] < MIN_TRAIN or counts["eval"] == 0:
        reason = f"too little data: {counts['train']} train, {counts['eval']} eval (needs {MIN_TRAIN} and 1)"
        return _write(done, {"status": "skipped", "name": specialist.name, "reason": reason, **counts})

    if report_file.is_file():
        report = TrainReport(**json.loads(report_file.read_text(encoding="utf-8")))
    else:
        cfg = load_train_config()
        cfg.train_file, cfg.eval_file = out / "data" / "train.jsonl", out / "data" / "eval.jsonl"
        cfg.out_dir, cfg.epochs = out, specialist.epochs
        cfg.time_budget_min = max(MIN_TRAIN_MINUTES, min(int(remaining_min) - RESERVE_MIN, MAX_TRAIN_MIN))
        report = train_fn(cfg, out)
        _write(report_file, asdict(report))

    candidate = candidate_file(out)
    if candidate is None:
        candidate = export_fn(out, cfg_base_model())
        shutil.rmtree(out / "merged", ignore_errors=True)  # 8 GB of merged weights, no longer needed

    tasks = specialist_tasks(specialist, tasks_dir)
    cand_file = out / "eval_cand.json"
    if cand_file.is_file():
        cand = EvalResult.load(cand_file)
    else:
        cand = eval_fn(candidate, tasks=tasks, log=out / "server.log")
        cand.save(cand_file)
    base = _base_result(tasks, baseline_dir, eval_fn)
    passed, why = gate(*gate_inputs(base, cand, asdict(report)))
    _write(out / "gate.json", {"passed": passed, "reason": why})
    status = {
        "status": "promoted" if passed else "rejected",
        "name": specialist.name,
        "reason": why,
        **counts,
    }
    if passed:
        target = models_dir / "specialists" / f"{specialist.name}.gguf"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, target)
        status["model"] = str(target)
    return _write(done, status)


def cfg_base_model() -> Path:
    return load_train_config().base_model


def stop_llama_servers() -> None:
    from petru_train.nightly import stop_llama_servers as stop

    stop()


def run_specialists(
    run: str,
    deadline: datetime,
    specialists: list[Specialist] | None = None,
    runs_dir: Path = RUNS_DIR,
    clock: Callable[[], datetime] = datetime.now,
    one: Callable = run_one,
) -> list[dict]:
    """The specialists in rotation order until the deadline; the rotation state is updated after each."""
    state_file = runs_dir / "specialists.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
    results = []
    for specialist in rotation(specialists if specialists is not None else load_specialists(), state):
        remaining = (deadline - clock()).total_seconds() / 60
        stop_llama_servers()
        result = one(specialist, runs_dir / run, remaining)
        results.append(result)
        print(
            f"specialist {specialist.name}: {result['status']} {result.get('reason', '')}".strip(), flush=True
        )
        if result["status"] == "no time":
            break
        if result["status"] in ("promoted", "rejected"):
            state[specialist.name] = run
            _write(state_file, state)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the language specialists until a deadline.")
    parser.add_argument("--run", required=True)
    parser.add_argument("--until", required=True, help="ISO time, e.g. 2026-10-27T11:00")
    parser.add_argument("--only", default="", help="comma-separated specialist names, in this order")
    args = parser.parse_args(argv)
    specialists = load_specialists()
    if args.only:
        wanted = [name.strip() for name in args.only.split(",") if name.strip()]
        by_name = {s.name: s for s in specialists}
        specialists = [by_name[name] for name in wanted]
    results = run_specialists(args.run, datetime.fromisoformat(args.until), specialists)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
