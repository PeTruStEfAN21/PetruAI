"""Keep every path the model hands us inside the project root."""

from __future__ import annotations

from pathlib import Path


class OutsideProjectError(Exception):
    """The path resolves outside the project root."""


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def resolve_in_project(path: str, root: Path) -> Path:
    """Accept '/', '\\', relative or absolute paths; refuse anything that escapes `root`."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not is_inside(resolved, root):
        raise OutsideProjectError(f"{path!r} is outside the project root {str(root)!r}")
    return resolved
