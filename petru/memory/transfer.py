"""Move what Petru learned between machines: a zip with global memory, project memory, decisions and journal.
The code index is never exported; it is rebuilt from the code."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from petru.memory.store import INDEX_FILE, MemoryStore, memory_dir, parse_note

_MEMORY_FILE = re.compile(r"^(global|project/memory)/([A-Za-z0-9._-]+\.md)$")


def export_memory(
    zip_path: Path, project_root: Path, include_global: bool = True, include_project: bool = True
) -> int:
    entries: list[tuple[Path, str]] = []
    if include_global:
        root = memory_dir("global", project_root)
        entries += [(p, f"global/{p.name}") for p in sorted(root.glob("*.md"))] if root.is_dir() else []
    if include_project:
        root = memory_dir("project", project_root)
        entries += (
            [(p, f"project/memory/{p.name}") for p in sorted(root.glob("*.md"))] if root.is_dir() else []
        )
        for name in ("DECISIONS.md", "journal.sqlite"):
            path = project_root / ".petru" / name
            if path.is_file():
                entries.append((path, f"project/{name}"))
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in entries:
            zf.write(path, arcname)
    return len(entries)


def _safe(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return bool(parts) and not PurePosixPath(name).is_absolute() and ".." not in parts and "\\" not in name


def _merge_decisions(target: Path, incoming: str) -> bool:
    lines = [line for line in incoming.splitlines() if line.startswith("- ")]
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(incoming, encoding="utf-8", newline="\n")
        return True
    have = set(target.read_text(encoding="utf-8").splitlines())
    new = [line for line in lines if line not in have]
    if new:
        with target.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(new) + "\n")
    return bool(new)


def import_memory(zip_path: Path, project_root: Path) -> dict[str, int]:
    counts = {"added": 0, "merged": 0, "skipped": 0}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            if info.is_dir():
                continue
            if not _safe(name):
                counts["skipped"] += 1
                continue
            match = _MEMORY_FILE.match(name)
            if match:
                if match[2] == INDEX_FILE:
                    continue  # the index is rebuilt by the store
                note = parse_note(zf.read(info).decode("utf-8", errors="replace"))
                if note is None:
                    counts["skipped"] += 1
                    continue
                scope = "global" if match[1] == "global" else "project"
                outcome = MemoryStore(memory_dir(scope, project_root)).merge(*note)
                if outcome != "unchanged":
                    counts[outcome] += 1
            elif name == "project/DECISIONS.md":
                target = project_root / ".petru" / "DECISIONS.md"
                existed = target.exists()
                if _merge_decisions(target, zf.read(info).decode("utf-8", errors="replace")):
                    counts["merged" if existed else "added"] += 1
            elif name == "project/journal.sqlite":
                target = project_root / ".petru" / "journal.sqlite"
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    counts["added"] += 1
            else:
                counts["skipped"] += 1
    return counts
