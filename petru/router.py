"""Pick the language specialist for a project (`petru --model auto`): its files, or the request when new."""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

SPECIALIST_BY_EXT = {
    ".py": "python", ".ts": "web", ".tsx": "web", ".js": "web", ".jsx": "web", ".mjs": "web", ".vue": "web",
    ".svelte": "web", ".html": "web", ".css": "web", ".dart": "flutter", ".java": "jvm", ".kt": "jvm",
    ".kts": "jvm", ".scala": "jvm", ".cs": "dotnet", ".c": "systems", ".h": "systems", ".cpp": "systems",
    ".cc": "systems", ".hpp": "systems", ".go": "go", ".rs": "rust", ".php": "php", ".rb": "ruby",
    ".swift": "swift", ".r": "data-r", ".sh": "scripting", ".ps1": "scripting", ".sql": "scripting",
}  # fmt: skip
MARKERS = {
    "pubspec.yaml": "flutter", "package.json": "web", "tsconfig.json": "web", "go.mod": "go",
    "Cargo.toml": "rust", "pom.xml": "jvm",
    "build.gradle.kts": "jvm", "build.gradle": "jvm", "CMakeLists.txt": "systems",
    "composer.json": "php", "Gemfile": "ruby", "Package.swift": "swift", "DESCRIPTION": "data-r",
    "pyproject.toml": "python", "requirements.txt": "python", "setup.py": "python",
}  # fmt: skip
MARKER_WEIGHT = 10  # one build file says more than one source file
SKIP_DIRS = {
    ".git",
    ".petru",
    "node_modules",
    ".venv",
    "venv",
    ".dart_tool",
    "build",
    "dist",
    "target",
    "__pycache__",
}
MAX_FILES = 3000
PYTHON_WEB = ("django", "flask", "fastapi", "starlette", "aiohttp", "litestar", "quart", "sanic", "tornado")
PYTHON_DATA = (
    "pandas",
    "numpy",
    "scikit-learn",
    "sklearn",
    "polars",
    "xarray",
    "dask",
    "statsmodels",
    "seaborn",
)
REQUEST_WORDS = {
    "flutter": "flutter", "dart": "flutter", "typescript": "web", "javascript": "web", "react": "web",
    "express": "web", "node": "web", "python": "python", "django": "python-web", "flask": "python-web",
    "fastapi": "python-web", "pandas": "python-data", "java": "jvm", "kotlin": "jvm", "c#": "dotnet",
    ".net": "dotnet", "c++": "systems", "go": "go", "golang": "go", "rust": "rust", "php": "php",
    "ruby": "ruby", "swift": "swift", "sql": "scripting", "powershell": "scripting", "bash": "scripting",
}  # fmt: skip


def _python_branch(root: Path) -> str:
    text = " ".join(
        (root / name).read_text(encoding="utf-8", errors="replace").lower()
        for name in ("requirements.txt", "pyproject.toml", "setup.py")
        if (root / name).is_file()
    )
    if any(word in text for word in PYTHON_WEB):
        return "python-web"
    if any(word in text for word in PYTHON_DATA):
        return "python-data"
    return "python"


def project_specialist(root: Path) -> str | None:
    """The specialist whose languages dominate the project, or None for an empty folder."""
    if not root.is_dir():
        return None
    counts: Counter[str] = Counter()
    for marker, specialist in MARKERS.items():
        if (root / marker).is_file():
            counts[specialist] += MARKER_WEIGHT
    seen = 0
    for _dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            specialist = SPECIALIST_BY_EXT.get(Path(filename).suffix.lower())
            if specialist:
                counts[specialist] += 1
            seen += 1
        if seen > MAX_FILES:
            break
    if not counts:
        return None
    specialist = counts.most_common(1)[0][0]
    return _python_branch(root) if specialist == "python" else specialist


def request_specialist(text: str) -> str | None:
    """For a new project: the first language the request names."""
    words = re.findall(r"[a-z+#.]+", text.lower())
    for word in words:
        if word in REQUEST_WORDS:
            return REQUEST_WORDS[word]
    return None


def choose_tier(root: Path, tiers: dict, fallback: str, request: str = "") -> str:
    """`tuned-<specialist>` when that specialist was promoted (the general Python one stands in for its two
    branches), else `fallback`."""
    specialist = project_specialist(root) or (request_specialist(request) if request else None)
    return _promoted(specialist, tiers, fallback)


def piece_tier(root: Path, files: list[str], tiers: dict, fallback: str) -> str:
    """Team mode: the promoted specialist for the language of a delegated piece's files, else `fallback`."""
    counts = Counter(SPECIALIST_BY_EXT.get(Path(name).suffix.lower()) for name in files)
    counts.pop(None, None)
    if not counts:
        return fallback
    specialist = counts.most_common(1)[0][0]
    return _promoted(_python_branch(root) if specialist == "python" else specialist, tiers, fallback)


def _promoted(specialist: str | None, tiers: dict, fallback: str) -> str:
    if specialist is None:
        return fallback
    for candidate in (specialist, "python" if specialist.startswith("python-") else None):
        if candidate and f"tuned-{candidate}" in tiers:
            return f"tuned-{candidate}"
    return fallback
