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


def _difficulty(task: Path) -> int:
    return int(tomllib.loads(task.read_text(encoding="utf-8")).get("difficulty", 0))


def interleave(tasks: list[Path], kept_by_language: Counter) -> list[Path]:
    """Breadth first: one exercise per language in turn, the languages with the fewest kept trajectories
    first; inside a language, the easier exercises first."""
    by_language: dict[str, list[Path]] = defaultdict(list)
    for path in tasks:
        by_language[language_for(task_name(path))].append(path)
    for paths in by_language.values():
        paths.sort(key=lambda p: (_difficulty(p), task_name(p)))
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
    kept = Counter()
    for name, count in _load_state(state_file)["kept"].items():
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
            samples_per_task=1,
            attempts_per_task=2,
            max_tokens=0,
            base_url=f"http://127.0.0.1:{PORT}/v1",
            attempt_timeout_s=3600,
            max_minutes=minutes,
            state_file=state_file,
            parallel=parallel,
        )
        return gen(cfg, tasks=ordered)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
