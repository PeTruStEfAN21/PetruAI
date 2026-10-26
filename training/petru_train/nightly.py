"""The night run: build -> trajectories -> train -> export -> eval_base -> eval_cand -> promote, resumable.

Every finished step is recorded in runs/<run>/state.json; a rerun of the same --run skips what is done.
A failing step stops the run with the error recorded; the next invocation retries from that step.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

TRAINING_DIR = Path(__file__).resolve().parents[1]
RUNS_DIR = TRAINING_DIR / "runs"
STEPS = ["build", "trajectories", "train", "export", "eval_base", "eval_cand", "promote"]
OPTIONAL_STEPS = {"trajectories"}  # a failure is noted and the night goes on
EVAL_RESERVE_MIN = 75  # minutes kept free after training for export + the two evaluations


class SkipStep(Exception):
    """Raised by a step that has nothing to do; recorded as a note, not an error."""


@dataclass
class RunContext:
    run: str
    runs_dir: Path
    hours: float
    clock: Callable[[], float] = time.monotonic
    started: float | None = None
    notes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.started is None:
            self.started = self.clock()

    @property
    def run_dir(self) -> Path:
        return self.runs_dir / self.run

    @property
    def baseline_dir(self) -> Path:
        return self.runs_dir / "baseline"

    def remaining_minutes(self) -> float:
        return max(0.0, self.hours * 60 - (self.clock() - (self.started or 0.0)) / 60)

    def skip(self, reason: str) -> None:
        raise SkipStep(reason)


@dataclass
class RunState:
    run: str
    done: list[str]
    started: str
    updated: str
    error: str | None
    notes: dict[str, str] = field(default_factory=dict)

    def save(self, run_dir: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        self.updated = _now()
        (run_dir / "state.json").write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_state(run_dir: Path) -> RunState | None:
    path = run_dir / "state.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return RunState(**data)


# --- the real steps -------------------------------------------------------


def step_build(ctx: RunContext) -> None:
    from petru_train.build import build, load_dataset_config

    stats = build(load_dataset_config())
    ctx.notes["build"] = f"train={stats['train']} eval={stats['eval']}"


def step_trajectories(ctx: RunContext) -> None:
    from petru_train.trajectories import generate, load_traj_config

    cfg = load_traj_config()
    third = int(ctx.remaining_minutes() // 3)  # never let extra data eat the training time
    cfg.max_minutes = min(cfg.max_minutes or third, third)
    stats = generate(cfg)
    ctx.notes["trajectories"] = f"kept={sum(stats['kept'].values())}"
    step_build(ctx)  # the new trajectories join the dataset


def stop_llama_servers() -> None:
    """A leftover llama-server (from trajectories) would hold VRAM and push training into shared memory."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/IM", "llama-server.exe", "/F"], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)


def step_train(ctx: RunContext) -> None:
    from petru_train.train import load_train_config, train

    stop_llama_servers()
    cfg = load_train_config()
    budget = int(ctx.remaining_minutes()) - EVAL_RESERVE_MIN
    cfg.time_budget_min = max(10, budget)
    report = train(cfg, ctx.run_dir)
    ctx.notes["train"] = (
        f"steps={report.steps} train_loss={report.train_loss:.4f} eval_loss={report.eval_loss:.4f}"
    )


def step_export(ctx: RunContext) -> None:
    from petru_train.env import MODEL_DIR
    from petru_train.export import export_run

    candidate = export_run(ctx.run_dir, MODEL_DIR)
    ctx.notes["export"] = f"{candidate.name} {candidate.stat().st_size / 1e9:.2f} GB"


def step_eval_base(ctx: RunContext) -> None:
    from petru_train.evaluate import (
        BASE_GGUF,
        REQUESTS_FILE,
        TASK_LIMIT,
        TASKS_DIR,
        EvalResult,
        evaluate,
        tasks_signature,
    )

    target = ctx.baseline_dir / "eval_base.json"
    if target.is_file() and EvalResult.load(target).signature == tasks_signature(
        TASKS_DIR, REQUESTS_FILE, TASK_LIMIT
    ):
        ctx.skip("baseline already evaluated on these tasks (they do not depend on the dataset)")
    result = evaluate(BASE_GGUF, log=ctx.baseline_dir / "server.log")
    result.save(target)
    ctx.notes["eval_base"] = f"tools={result.tool_validity} tasks={result.task_pass}"


def step_eval_cand(ctx: RunContext) -> None:
    from petru_train.evaluate import EvalResult, evaluate, gate, gate_inputs
    from petru_train.export import candidate_file

    candidate = candidate_file(ctx.run_dir)
    if candidate is None:
        raise RuntimeError("no quantized candidate: the export step did not produce one")
    result = evaluate(candidate, log=ctx.run_dir / "server.log")
    result.save(ctx.run_dir / "eval_cand.json")
    report = json.loads((ctx.run_dir / "train_report.json").read_text(encoding="utf-8"))
    base, result = gate_inputs(EvalResult.load(ctx.baseline_dir / "eval_base.json"), result, report)
    passed, why = gate(base, result)
    (ctx.run_dir / "gate.json").write_text(
        json.dumps({"passed": passed, "reason": why}, indent=2), encoding="utf-8"
    )
    ctx.notes["eval_cand"] = (
        f"loss={result.loss} tools={result.tool_validity} tasks={result.task_pass}; {why}"
    )


def step_promote(ctx: RunContext) -> None:
    from petru_train.export import promote

    gate_file = ctx.run_dir / "gate.json"
    gate = json.loads(gate_file.read_text(encoding="utf-8")) if gate_file.is_file() else {"passed": False}
    if not gate.get("passed"):
        ctx.skip(f"gate not passed: {gate.get('reason', 'no gate.json')}")
    ctx.notes["promote"] = f"promoted {promote(ctx.run_dir)}"


DEFAULT_STEPS: dict[str, Callable[[RunContext], None]] = {
    "build": step_build,
    "trajectories": step_trajectories,
    "train": step_train,
    "export": step_export,
    "eval_base": step_eval_base,
    "eval_cand": step_eval_cand,
    "promote": step_promote,
}


def run_nightly(
    run: str,
    hours: float,
    steps: dict[str, Callable[[RunContext], None]] = DEFAULT_STEPS,
    runs_dir: Path = RUNS_DIR,
    clock: Callable[[], float] = time.monotonic,
    skip: tuple[str, ...] | list[str] = (),
) -> RunState:
    ctx = RunContext(run=run, runs_dir=runs_dir, hours=hours, clock=clock)
    state = load_state(ctx.run_dir) or RunState(run, [], _now(), _now(), None)
    state.error = None
    state.save(ctx.run_dir)
    for name in STEPS:
        if name in state.done:
            continue
        if name in skip:
            state.notes[name] = "skipped by flag"
            state.done.append(name)
            state.save(ctx.run_dir)
            continue
        print(f"[{_now()}] {name}: start ({ctx.remaining_minutes():.0f} min left)", flush=True)
        try:
            steps[name](ctx)
        except SkipStep as exc:
            state.notes[name] = str(exc)
        except Exception as exc:
            if name in OPTIONAL_STEPS:  # extra data is a bonus; the night still trains on what exists
                state.notes[name] = f"failed (optional, continuing): {type(exc).__name__}: {exc}"
                state.done.append(name)
                state.save(ctx.run_dir)
                print(f"[{_now()}] {name}: FAILED (optional) {exc}", flush=True)
                continue
            state.error = f"{name}: {type(exc).__name__}: {exc}"
            state.notes[name] = traceback.format_exc()[-2000:]
            state.save(ctx.run_dir)
            print(f"[{_now()}] {name}: FAILED {exc}", flush=True)
            return state
        else:
            if name in ctx.notes:
                state.notes[name] = ctx.notes[name]
        state.done.append(name)
        state.save(ctx.run_dir)
        print(f"[{_now()}] {name}: done {state.notes.get(name, '')}", flush=True)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run (or resume) one training night.")
    parser.add_argument("--run", required=True, help="run name, e.g. 2026-10-27")
    parser.add_argument("--hours", type=float, default=7.0)
    parser.add_argument("--skip-trajectories", action="store_true")
    parser.add_argument("--skip", nargs="*", default=[], help="steps to mark done without running")
    args = parser.parse_args(argv)
    skip = list(args.skip) + (["trajectories"] if args.skip_trajectories else [])
    state = run_nightly(args.run, args.hours, skip=skip)
    print(json.dumps(asdict(state), indent=2, ensure_ascii=False))
    return 1 if state.error else 0


if __name__ == "__main__":
    sys.exit(main())
