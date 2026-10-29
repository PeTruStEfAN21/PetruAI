"""The 35B teacher on the validated Exercism pool: verified trajectories in every language, until a deadline.

One llama-server holds the teacher with a slot per parallel attempt (experts in RAM, the rest on the GPU), so
one agent generates while the others compile and run their tests. Progress is global (one state file), so
every session continues where the last one stopped: one kept trajectory per exercise, breadth first over
languages.

    py -3.14 -m uv run python -m petru_train.teacher --until 2026-10-28T08:00 --parallel 3
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime
from itertools import zip_longest
from pathlib import Path

from petru_train.exercism import TASKS_DIR, validated_tasks
from petru_train.server import REPO_ROOT, start_server, stop, wait_healthy
from petru_train.trajectories import TrajConfig, _load_state, generate, language_for, task_name

TRAINING_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = TRAINING_DIR / "data"
TEACHER_GGUF = REPO_ROOT / "infra" / "llama.cpp" / "models" / "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"
SLOT_CTX = 32768  # the quality tier's context, per agent
PORT = 8082
OUT = DATA_DIR / "trajectories-exercism.jsonl"
STATE = DATA_DIR / "trajectories-exercism.state.json"
SAMPLES_PER_TASK, ATTEMPTS_PER_TASK = 1, 2  # breadth: one verified trajectory per exercise
NOTHING_LEFT = 3  # exit code: every validated exercise has its trajectory or used its attempts
EASY_UP_TO, MEDIUM_UP_TO = 2, 5  # Exercism difficulty (1-10) bands: easy, medium, then hard


def _difficulty(task: Path) -> int:
    return int(tomllib.loads(task.read_text(encoding="utf-8")).get("difficulty", 0))


def _easy_and_medium_in_turn(paths: list[Path]) -> list[Path]:
    """Easy and medium exercises take turns, so the student sees real problems early, not only after every
    warm-up; the hard ones come last. Each band keeps its easier exercises first."""
    paths = sorted(paths, key=lambda p: (_difficulty(p), task_name(p)))
    easy = [p for p in paths if _difficulty(p) <= EASY_UP_TO]
    medium = [p for p in paths if EASY_UP_TO < _difficulty(p) <= MEDIUM_UP_TO]
    hard = [p for p in paths if _difficulty(p) > MEDIUM_UP_TO]
    return [p for pair in zip_longest(easy, medium) for p in pair if p is not None] + hard


def interleave(tasks: list[Path], kept_by_language: Counter) -> list[Path]:
    """Breadth first: one exercise per language in turn, the languages with the fewest kept trajectories
    first; inside a language, easy and medium exercises in turn, then the hard ones."""
    by_language: dict[str, list[Path]] = defaultdict(list)
    for path in tasks:
        by_language[language_for(task_name(path))].append(path)
    for language, paths in by_language.items():
        by_language[language] = _easy_and_medium_in_turn(paths)
    languages = sorted(by_language, key=lambda lang: (kept_by_language[lang], lang))
    ordered = []
    for index in range(max((len(p) for p in by_language.values()), default=0)):
        ordered += [by_language[lang][index] for lang in languages if index < len(by_language[lang])]
    return ordered


def run(
    until: datetime,
    parallel: int = 3,
    clock: Callable[[], datetime] = datetime.now,
    gen: Callable = generate,
    state_file: Path = STATE,
    out: Path = OUT,
) -> dict:
    tasks = validated_tasks(split="train")
    if not tasks:
        print("no validated tasks: run `python -m petru_train.exercism validate` first", flush=True)
        return {}
    state = _load_state(state_file)
    open_tasks = [
        t for t in tasks
        if int(state["kept"].get(task_name(t), 0)) < SAMPLES_PER_TASK
        and int(state["attempts"].get(task_name(t), 0)) < ATTEMPTS_PER_TASK
    ]  # fmt: skip
    if not open_tasks:
        print("nothing left to teach: every validated exercise is done", flush=True)
        return {"open": 0}
    kept = Counter()
    for name, count in state["kept"].items():
        kept[language_for(name)] += int(count)
    ordered = interleave(tasks, kept)
    minutes = int((until - clock()).total_seconds() // 60)
    log = DATA_DIR / "teacher-server.log"
    proc = start_server(
        TEACHER_GGUF, PORT, SLOT_CTX * parallel, log=log, extra=("--cpu-moe", "--parallel", str(parallel))
    )
    try:
        if not wait_healthy(PORT, timeout_s=900, proc=proc):
            raise RuntimeError(f"the teacher did not start; see {log}")
        cfg = TrajConfig(
            tasks_dir=TASKS_DIR,
            out=out,
            tier="quality",
            samples_per_task=SAMPLES_PER_TASK,
            attempts_per_task=ATTEMPTS_PER_TASK,
            max_tokens=0,
            base_url=f"http://127.0.0.1:{PORT}/v1",
            attempt_timeout_s=3600,
            max_minutes=minutes,
            state_file=state_file,
            parallel=parallel,
        )
        return {**gen(cfg, tasks=ordered), "open": len(open_tasks)}
    finally:
        stop(proc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verified trajectories from the 35B teacher on Exercism tasks."
    )
    parser.add_argument("--until", required=True, help="ISO time; no new attempt starts after it")
    parser.add_argument("--parallel", type=int, default=3)
    args = parser.parse_args(argv)
    stats = run(datetime.fromisoformat(args.until), parallel=args.parallel)
    kept = sum(stats.get("kept", {}).values())
    print(json.dumps({"tasks": stats.get("tasks", 0), "kept_total": kept}), flush=True)
    return main_exit(stats)


def main_exit(stats: dict) -> int:
    return NOTHING_LEFT if stats.get("open") == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
