"""The full-screen view's side panel: the plan, the files changed, the team and the model, as plain lines."""

from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from petru.agent import team

if TYPE_CHECKING:
    from petru.app import App

MAX_FILES = 12


def changed_files(project: Path, limit: int = MAX_FILES) -> list[str]:
    """The project's changes since the last commit: `+ new`, `~ modified`, `- deleted`, by path; [] outside a
    git repository."""
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=off", "status", "--porcelain", "--untracked-files=all"],
            cwd=project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except OSError, subprocess.TimeoutExpired:
        return []
    if out.returncode != 0:
        return []
    marked = []
    for line in out.stdout.splitlines():
        code, path = line[:2], line[3:]
        mark = "-" if "D" in code else "+" if code == "??" or "A" in code else "~"
        marked.append((path, mark))
    lines = [f"{mark} {path}" for path, mark in sorted(marked)]
    return lines if len(lines) <= limit else [*lines[:limit], f"… {len(lines) - limit} more"]


def _team_lines(app: App) -> list[str]:
    if not app.team_on:
        return ["off"]
    registry = app.agent.registry
    choice, delegate = registry.get("choose_mode"), registry.get("delegate")
    reason = getattr(choice, "reason", None)
    head = f"on: {getattr(choice, 'mode', None) or 'not chosen yet'}{f' ({reason})' if reason else ''}"
    lines = [f"{head} · {getattr(delegate, 'calls', 0)} delegations"]
    by_author: dict[str, list[str]] = defaultdict(list)
    for path, who in sorted(team.credits(registry).items()):
        by_author[who].append(path)
    lines += [f"{who}: {', '.join(paths)}" for who, paths in sorted(by_author.items())]
    return lines


def panel_sections(app: App, files: list[str]) -> list[tuple[str, list[str]]]:
    plan = app.session.plan
    speed = app.speed()
    model = f"{app.session.tier} · context {app.context_share()}%{f' · {speed:.0f} tok/s' if speed else ''}"
    return [
        ("Plan", [f"{i}. {step}" for i, step in enumerate(plan.steps, start=1)] if plan else ["no plan yet"]),
        ("Files", files or ["no changes"]),
        ("Team", _team_lines(app)),
        ("Model", [model]),
    ]
