"""Turn queued commits into 2-4 line summaries (what changed and why) with the local model, lazily."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from petru.journal.store import Journal
from petru.providers.base import ChatProvider

MAX_DIFF_CHARS = 6000
SYSTEM = (
    "You write a project's change journal. Summarize the commit in 2 to 4 short lines: what changed and why "
    "(the intent), naming files only when it helps. No preamble, no bullet symbols, no code."
)


def _git(project: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(project), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return proc.stdout if proc.returncode == 0 else ""


def _commit_time(project: Path, rev: str) -> float:
    out = _git(project, "log", "-1", "--format=%ct", rev).strip()
    return float(out) if out else 0.0


def commit_prompt(project: Path, journal: Journal, sha: str) -> str:
    message = _git(project, "log", "-1", "--format=%B", sha).strip()
    stat = _git(project, "show", "--stat", "--format=", sha).strip()
    diff = _git(project, "show", "--format=", "--unified=2", sha)
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n[diff truncated]"
    since = _commit_time(project, f"{sha}^")
    saved = sorted({e.path for e in journal.recent_events(since_ts=since, limit=500)})
    parts = [f"Commit message:\n{message}", f"Files:\n{stat}", f"Diff:\n{diff}"]
    if saved:
        parts.append("Files edited while working on it:\n" + "\n".join(saved[:40]))
    return "\n\n".join(parts)


def summarize_pending(
    project: Path, provider: ChatProvider, limit: int = 5, notify: Callable[[int], None] | None = None
) -> int:
    """Summarize queued commits; `notify(n)` is called first when there is work, so a UI can say why it waits.
    An empty answer closes the commit (status done, empty summary) instead of retrying it forever."""
    db = project / ".petru" / "journal.sqlite"
    if not db.is_file():
        return 0
    journal = Journal(db)
    done = 0
    try:
        pending = journal.pending_commits(limit)
        if pending and notify is not None:
            notify(len(pending))
        for sha, _ts in pending:
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": commit_prompt(project, journal, sha)},
            ]
            summary = provider.complete(messages, None, max_tokens=200).content.strip()
            journal.set_summary(sha, summary)
            done += bool(summary)
    finally:
        journal.close()
    return done


def journal_prompt_section(project: Path, n: int = 5, max_tokens: int = 400) -> str:
    db = project / ".petru" / "journal.sqlite"
    if not db.is_file():
        return ""
    journal = Journal(db)
    try:
        summaries = journal.recent_summaries(n)
    finally:
        journal.close()
    if not summaries:
        return ""
    lines = [f"- {sha[:7]}: {' '.join(summary.split())}" for sha, summary in summaries]
    text = "## Recent commits (journal)\n" + "\n".join(lines)
    return text[: max_tokens * 4]
