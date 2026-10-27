"""The projects the team built in a bench run, gathered with who wrote which file, to show what it can do.

    py -3.14 -m uv run python -m petru_train.showcase runs/bench/bench-2026-10-27.json ../showcase

Each kept team project is copied to <out>/<task>/ with a SHOWCASE.md: the task, the result against the 35B
alone, and every file credited to the lead, the assistant or the given acceptance tests. <out>/README.md is
the index.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from petru_train.bench import BENCH_DIR


def _calls(messages: list[dict]) -> list[tuple[str, dict]]:
    found = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            args = function.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            found.append((function.get("name", ""), args if isinstance(args, dict) else {}))
    return found


def _norm(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix().removeprefix("./")


def authors(messages: list[dict], given: set[str]) -> Callable[[str], str]:
    """Who wrote a file: the lead, the assistant (the files it was handed), or the given acceptance tests."""
    delegated, lead = set(), set()
    for name, args in _calls(messages):
        if name == "delegate":
            delegated |= {_norm(str(f)) for f in args.get("files") or []}
        elif name in ("write_file", "edit_file") and args.get("path"):
            lead.add(_norm(str(args["path"])))

    def credit(path: str) -> str:
        if path in given:
            return "given (acceptance tests)"
        if path in delegated:
            return "assistant, revised by the lead" if path in lead else "assistant"
        return "lead"

    return credit


def _minutes(seconds) -> str:
    return f"{round(seconds / 60)} min" if isinstance(seconds, int | float) else "-"


def _project_page(task: str, spec: dict, row: dict, solo: dict, files: list[str], credit) -> str:
    lines = [
        f"# {task}",
        "",
        "Built by the PetruAI team: Qwen3.6-35B-A3B leading, Qwen3.5-4B assisting, both run locally.",
        "",
        "## Task",
        "",
        spec.get("prompt", "").strip(),
        "",
        "## Result",
        "",
        f"- Acceptance tests: {'passed' if row.get('passed') else 'failed'}",
        f"- Time: {_minutes(row.get('seconds'))} as a team, "
        f"{_minutes(solo.get('seconds'))} for the 35B alone",
        f"- Pieces handed to the assistant: {row.get('delegations', 0)}",
        "",
        "## Who wrote what",
        "",
        "| File | Written by |",
        "|---|---|",
        *(f"| `{path}` | {credit(path)} |" for path in files),
        "",
    ]
    return "\n".join(lines)


def export(report: Path, out: Path, bench_dir: Path = BENCH_DIR) -> list[str]:
    """Copy every kept team project of `report` to `out` with its page; returns the tasks exported."""
    results = json.loads(report.read_text(encoding="utf-8")).get("results", [])
    runs = report.with_suffix("")
    solo = {r["task"]: r for r in results if r.get("mode") == "solo"}
    index = [
        "# What the PetruAI team built",
        "",
        "Projects from the team-against-solo bench: the 35B leads and hands simple pieces to a 4B assistant.",
        "Each folder has the code and a SHOWCASE.md with the task and who wrote which file.",
        "",
        "| Project | Tests | Team | 35B alone | Pieces delegated |",
        "|---|---|---|---|---|",
    ]
    exported = []
    for row in (r for r in results if r.get("mode") == "team"):
        task = row["task"]
        project = runs / f"{task}-team"
        if not project.is_dir():
            continue
        spec_file = bench_dir / task / "task.toml"
        spec = tomllib.loads(spec_file.read_text(encoding="utf-8")) if spec_file.is_file() else {}
        seed = bench_dir / task / spec.get("seed", "seed")
        given = (
            {p.relative_to(seed).as_posix() for p in seed.rglob("*") if p.is_file()}
            if seed.is_dir()
            else set()
        )
        transcript = runs / f"{task}-team.json"
        messages = (
            json.loads(transcript.read_text(encoding="utf-8")).get("messages", [])
            if transcript.is_file()
            else []
        )
        dest = out / task
        shutil.copytree(project, dest, dirs_exist_ok=True)
        files = sorted(p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file())
        page = _project_page(task, spec, row, solo.get(task, {}), files, authors(messages, given))
        (dest / "SHOWCASE.md").write_text(page, encoding="utf-8")
        tests = "passed" if row.get("passed") else "failed"
        minutes = (_minutes(row.get("seconds")), _minutes(solo.get(task, {}).get("seconds")))
        index.append(f"| {task} | {tests} | {minutes[0]} | {minutes[1]} | {row.get('delegations', 0)} |")
        exported.append(task)
    out.mkdir(parents=True, exist_ok=True)
    (out / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return exported


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gather the team's bench projects with who wrote what.")
    parser.add_argument("report", type=Path, help="a bench report (runs/bench/<name>.json)")
    parser.add_argument("out", type=Path, help="the folder to write")
    args = parser.parse_args(argv)
    print("exported:", ", ".join(export(args.report, args.out)) or "nothing (no kept team projects)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
