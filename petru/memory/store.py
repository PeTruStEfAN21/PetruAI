"""Typed memory notes with a capped MEMORY.md index. Updates are incremental: new facts are appended, never
rewritten, so a small model cannot erase what it learned earlier."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

MEMORY_TYPES = ("user", "feedback", "project", "reference")
INDEX_FILE = "MEMORY.md"
INDEX_MAX_LINES = 200
RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
Scope = Literal["project", "global"]
_INDEX_LINE = re.compile(r"^- \[(?P<name>.+?)\]\((?P<file>[^)]+)\) — (?P<description>.*)$")


def petru_home() -> Path:
    return Path(os.environ.get("PETRU_HOME") or Path.home() / ".petru")


def memory_dir(scope: Scope, project_root: Path) -> Path:
    if scope == "global":
        return petru_home() / "memory"
    return project_root / ".petru" / "memory"


def slugify(name: str) -> str:
    """A file-safe slug: ascii [a-z0-9-], at most 60 chars, never empty, never a Windows device name."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")[:60].strip("-")
    if not slug:
        slug = "memory"
    if slug in RESERVED:
        slug = f"{slug}-note"
    return slug


@dataclass
class Memory:
    name: str
    description: str
    type: str
    body: str
    path: Path


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


class MemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    # -- index ----------------------------------------------------------------

    def _index_path(self) -> Path:
        return self.root / INDEX_FILE

    def _read_index(self) -> list[tuple[str, str, str]]:
        path = self._index_path()
        if not path.is_file():
            return []
        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _INDEX_LINE.match(line)
            if match:
                entries.append((match["name"], match["file"], match["description"]))
        return entries

    def _write_index(self, entries: list[tuple[str, str, str]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        lines = [f"- [{name}]({file}) — {description}" for name, file, description in entries]
        self._index_path().write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n"
        )

    def index_text(self, max_lines: int = INDEX_MAX_LINES) -> str:
        path = self._index_path()
        if not path.is_file():
            return ""
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return "\n".join(lines[-max_lines:])

    # -- notes ----------------------------------------------------------------

    def _file_for(self, name: str) -> Path:
        return self.root / f"{slugify(name)}.md"

    def _read(self, path: Path) -> Memory | None:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\nname: (.*)\ndescription: (.*)\ntype: (.*)\n---\n(.*)$", text, re.DOTALL)
        if not match:
            return Memory(path.stem, "", "reference", text, path)
        return Memory(match[1], match[2], match[3], match[4].strip("\n"), path)

    def _write(self, memory: Memory) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        header = f"---\nname: {memory.name}\ndescription: {memory.description}\ntype: {memory.type}\n---\n"
        memory.path.write_text(header + "\n" + memory.body.strip("\n") + "\n", encoding="utf-8", newline="\n")

    def remember(self, name: str, description: str, type: str, content: str) -> Memory:
        if type not in MEMORY_TYPES:
            raise ValueError(f"type must be one of {', '.join(MEMORY_TYPES)}, not {type!r}")
        name, description, content = _one_line(name), _one_line(description), str(content).strip()
        path = self._file_for(name)
        existing = self._read(path)
        if existing is None:
            memory = Memory(name, description, type, content, path)
        else:
            bullet = f"- {date.today().isoformat()}: {_one_line(content)}"
            memory = Memory(existing.name, description or existing.description, type,
                            f"{existing.body}\n{bullet}", path)  # fmt: skip
        self._write(memory)
        entries = [entry for entry in self._read_index() if entry[1] != path.name]
        entries.append((memory.name, path.name, memory.description))
        self._write_index(entries[-INDEX_MAX_LINES:])
        return memory

    def get(self, name: str) -> Memory | None:
        return self._read(self._file_for(name))

    def forget(self, name: str) -> bool:
        path = self._file_for(name)
        if not path.is_file():
            return False
        path.unlink()
        self._write_index([entry for entry in self._read_index() if entry[1] != path.name])
        return True

    def all(self) -> list[Memory]:
        if not self.root.is_dir():
            return []
        found = [self._read(p) for p in sorted(self.root.glob("*.md")) if p.name != INDEX_FILE]
        return [m for m in found if m is not None]
