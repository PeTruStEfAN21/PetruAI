"""Verified trajectories: run the harness tasks with the local model and keep only what passed the checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass
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
}
Runner = Callable[[Path, "TrajConfig", int], dict]


@dataclass
class TrajConfig:
    tasks_dir: Path
    out: Path
    tier: str = "quality"
    samples_per_task: int = 3
    attempts_per_task: int = 4
    max_tokens: int = 12000
    base_url: str | None = None


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
        max_tokens=int(data.get("max_tokens", 12000)),
        base_url=data.get("base_url"),
    )


def language_for(task_name: str) -> str:
    return LANGUAGE_BY_PREFIX.get(task_name.split("_")[0].lower(), "unknown")


def result_to_sample(result: dict, task_name: str, max_tokens: int) -> Sample | None:
    """None unless the checks passed, the turn ended normally and the transcript fits the token budget."""
    if not result.get("passed") or result.get("stop_reason") or int(result.get("tokens") or 0) > max_tokens:
        return None
    # The recorded system prompt stays: it is what the agent sees at run time (rules, phase, packages).
    messages = list(result.get("messages", []))
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


def run_petru_task(task_path: Path, cfg: TrajConfig, attempt: int) -> dict:
    """One attempt through `python -m petru.trajectory` in the agent's environment, in a temporary project."""
    with tempfile.TemporaryDirectory(prefix="petru-traj-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "result.json"
        cmd = [
            "py", "-3.14", "-m", "uv", "run", "python", "-m", "petru.trajectory", str(task_path),
            "--out", str(out), "--tier", cfg.tier, "--project", str(Path(tmp) / "project"),
        ]  # fmt: skip
        if cfg.base_url:
            cmd += ["--base-url", cfg.base_url]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8")
        if not out.exists():
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
            return {
                "name": task_path.stem,
                "passed": False,
                "stop_reason": "runner error: " + " | ".join(tail),
            }
        return json.loads(out.read_text(encoding="utf-8"))


def _append_jsonl(path: Path, sample: Sample) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")


def _state_path(cfg: TrajConfig) -> Path:
    return cfg.out.with_name(cfg.out.name + ".state.json")


def _load_state(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"kept": {}, "attempts": {}}


def generate(cfg: TrajConfig, runner: Runner = run_petru_task) -> dict:
    """Per task: attempt until `samples_per_task` kept or `attempts_per_task` spent. Resumable."""
    tasks = sorted(cfg.tasks_dir.glob("*.toml"))
    state_path = _state_path(cfg)
    state = _load_state(state_path)
    for task in tasks:
        name = task.stem
        kept = int(state["kept"].get(name, 0))
        attempts = int(state["attempts"].get(name, 0))
        while kept < cfg.samples_per_task and attempts < cfg.attempts_per_task:
            attempts += 1
            result = runner(task, cfg, attempts)
            sample = result_to_sample(result, name, cfg.max_tokens)
            if sample is not None:
                _append_jsonl(cfg.out, sample)
                kept += 1
            verdict = "kept" if sample else "rejected"
            print(f"{name} attempt {attempts}: {verdict} ({kept}/{cfg.samples_per_task})")
            state["kept"][name], state["attempts"][name] = kept, attempts
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
        state["kept"].setdefault(name, kept)
        state["attempts"].setdefault(name, attempts)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
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
