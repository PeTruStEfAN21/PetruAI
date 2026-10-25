"""The append-only log of the user's decisions: .petru/DECISIONS.md in the project."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

HEADER = (
    "# Decizii\n\n"
    "Deciziile utilizatorului sunt finale. Intrările noi se adaugă la sfârșit; cea mai recentă câștigă.\n\n"
)


def decisions_path(root: Path) -> Path:
    return root / ".petru" / "DECISIONS.md"


def append_decisions(root: Path, entries: Iterable[str]) -> Path:
    path = decisions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(HEADER, encoding="utf-8", newline="\n")
    today = date.today().isoformat()
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for entry in entries:
            line = " ".join(str(entry).split())
            if line:
                fh.write(f"- {today}: {line}\n")
    return path


def read_decisions(root: Path, max_lines: int = 60) -> str:
    """The last `max_lines` decision entries, oldest first; empty when there are none."""
    path = decisions_path(root)
    if not path.is_file():
        return ""
    entries = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]
    return "\n".join(entries[-max_lines:])
