"""The projects the team built in a bench run, gathered with who wrote which file, to show what it can do.

    py -3.14 -m uv run python -m petru_train.showcase runs/bench/bench-2026-10-27.json ../showcase

Each kept team project of a bench task is copied to <out>/<task>/ with a SHOWCASE.md: the task, the result
against the 35B alone, and every file credited to the lead, the assistant or the task itself. <out>/README.md
is the index. The credits come from the run's result (the tools record them); for older runs they are read
from the transcript, in order, but only when it still holds every delegation (a summarised one does not).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tomllib
from functools import partial
from pathlib import Path, PurePosixPath

from petru_train.bench import BENCH_DIR

LEAD_MODEL = "Qwen3.6-35B-A3B"
NOT_RECORDED = "not recorded"


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


def infer_authors(messages: list[dict]) -> dict[str, str]:
    """Who created each file and who changed it after, from the lead's calls in order (the same credits the
    team's tools record): a file first named in a delegation is the assistant's."""
    creators: dict[str, str] = {}
    changers: dict[str, set[str]] = {}
    for name, args in _calls(messages):
        if name == "delegate":
            touched = [("assistant", _norm(str(f))) for f in args.get("files") or []]
        elif name in ("write_file", "edit_file") and args.get("path"):
            touched = [("lead", _norm(str(args["path"])))]
        else:
            continue
        for who, path in touched:
            if path not in creators:
                creators[path], changers[path] = who, set()
            elif who != creators[path]:
                changers[path].add(who)
    later = {"lead": "extended by the assistant", "assistant": "revised by the lead"}
    return {path: f"{who}, {later[who]}" if changers[path] else who for path, who in sorted(creators.items())}


def run_authors(data: dict, row: dict) -> dict[str, str] | None:
    """The run's credits: recorded by the tools, else read from a transcript that kept every delegation."""
    if "authors" in data:
        return data["authors"]
    messages = data.get("messages") or []
    kept = sum(1 for name, _ in _calls(messages) if name == "delegate")
    return infer_authors(messages) if kept == row.get("delegations", 0) else None


def _minutes(seconds) -> str:
    return f"{round(seconds / 60)} min" if isinstance(seconds, int | float) else "-"


def _byline(row: dict) -> str:
    if row.get("team_choice") == "solo":
        return f"Built by the PetruAI lead ({LEAD_MODEL}), which chose to work alone on this one."
    assistant = Path(row.get("assistant") or "Qwen3.5-4B").stem
    return f"Built by the PetruAI team: {LEAD_MODEL} leading, {assistant} assisting, both run locally."


def _credit(path: str, given: set[str], authors: dict[str, str] | None) -> str:
    if path in given:
        return "given with the task"
    if authors is None:
        return NOT_RECORDED
    return authors.get(path, "lead")  # what no write recorded, the lead's shell commands made


def _project_page(task: str, spec: dict, row: dict, solo: dict, files: list[str], credit) -> str:
    lines = [
        f"# {task}",
        "",
        _byline(row),
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
    if any(credit(path) == NOT_RECORDED for path in files):
        lines.append("Who wrote the other files was not recorded: this run's conversation was summarised.\n")
    return "\n".join(lines)


def export(report: Path, out: Path, bench_dir: Path = BENCH_DIR) -> list[str]:
    """Copy every kept team project of a bench task in `report` to `out` with its page; returns the tasks."""
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
        project, spec_file = runs / f"{task}-team", bench_dir / task / "task.toml"
        if not (project.is_dir() and spec_file.is_file()):
            continue
        spec = tomllib.loads(spec_file.read_text(encoding="utf-8"))
        seed = bench_dir / task / spec.get("seed", "seed")
        given = (
            {p.relative_to(seed).as_posix() for p in seed.rglob("*") if p.is_file()}
            if seed.is_dir()
            else set()
        )
        transcript = runs / f"{task}-team.json"
        data = json.loads(transcript.read_text(encoding="utf-8")) if transcript.is_file() else {}
        authors = run_authors(data, row)
        dest = out / task
        shutil.rmtree(dest, ignore_errors=True)  # no files left over from an earlier export
        shutil.copytree(project, dest)
        files = sorted(p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file())
        page = _project_page(
            task, spec, row, solo.get(task, {}), files, partial(_credit, given=given, authors=authors)
        )
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
