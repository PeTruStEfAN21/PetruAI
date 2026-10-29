"""The full-screen view's conversation: entries added from the agent thread, rendered to ANSI lines for the UI
thread, with a scroll position that follows the end until the user scrolls up."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

Kind = Literal["user", "text", "reasoning", "question", "tool", "notice"]
MIN_RENDER_WIDTH = 20  # narrower windows get these lines cut, not a crash
SPACED: tuple[Kind, ...] = ("user", "text", "reasoning", "question")  # a blank line before a new one of these


@dataclass
class Entry:
    kind: Kind
    body: str


def _renderable(entry: Entry):
    body = entry.body
    if entry.kind == "text":
        return Markdown(body)
    if entry.kind == "user":
        return Text(f"› {body}", style="bold")
    if entry.kind == "reasoning":
        return Text(body, style="dim italic")
    if entry.kind == "question":
        return Text(body, style="bold")
    if entry.kind == "notice":
        return Text(body, style="yellow")
    if body.startswith("▸ "):
        name, _, rest = body[2:].partition(" ")
        return Text.assemble(("▸ ", "cyan"), (name, "bold cyan"), f" {rest}" if rest else "")
    mark, rest = body.strip()[:1], body.strip()[1:]
    return Text.assemble("  ", (mark, "red" if mark == "✗" else "green"), rest)


class Transcript:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.entries: list[Entry] = []
        self.following = True
        self._offset = 0  # lines above the end, while not following
        self._total = 0  # lines at the last render, for scrolling
        self._cache: dict[tuple[int, int, int], list[str]] = {}  # (entry, body length, width) -> lines

    def add(self, kind: Kind, body: str) -> None:
        with self._lock:
            self.entries.append(Entry(kind, body))

    def stream(self, kind: Kind, delta: str) -> None:
        """Extend the last entry while it is of this kind; else start one (text after a tool line is new)."""
        with self._lock:
            if self.entries and self.entries[-1].kind == kind:
                self.entries[-1].body += delta
            else:
                self.entries.append(Entry(kind, delta))

    def _render(self, index: int, entry: Entry, width: int) -> list[str]:
        key = (index, len(entry.body), width)
        if key not in self._cache:
            console = Console(
                width=width, force_terminal=True, color_system="truecolor", legacy_windows=False
            )
            with console.capture() as capture:
                console.print(_renderable(entry))
            self._cache[key] = capture.get().rstrip("\n").split("\n")
        return self._cache[key]

    def lines(self, width: int) -> list[str]:
        width = max(width, MIN_RENDER_WIDTH)
        with self._lock:
            entries = list(enumerate(self.entries))
        out: list[str] = []
        previous: Kind | None = None
        for index, entry in entries:
            if out and entry.kind in SPACED and entry.kind != previous:
                out.append("")
            out.extend(self._render(index, entry, width))
            previous = entry.kind
        return out

    def visible(self, width: int, height: int) -> str:
        lines = self.lines(width)
        self._total, height = len(lines), max(height, 1)
        end = len(lines) if self.following else max(height, len(lines) - self._offset)
        return "\n".join(lines[max(0, end - height) : end])

    def page_up(self, height: int) -> None:
        self.following = False
        self._offset = min(self._offset + height, max(0, self._total - height))

    def page_down(self, height: int) -> None:
        self._offset = max(0, self._offset - height)
        self.following = self._offset == 0
