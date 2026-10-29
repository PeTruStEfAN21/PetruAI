"""Path, secret, language and commit-message filters shared by every dataset builder."""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import PurePosixPath

GENERATED_PATTERNS: list[str] = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pubspec.lock",
    "uv.lock",
    "poetry.lock",
    "Cargo.lock",
    "composer.lock",
    "Gemfile.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.g.dart",
    "*.freezed.dart",
    "*.pb.go",
    "*_pb2.py",
    "*.generated.*",
    "dist/",
    "build/",
    "node_modules/",
    ".dart_tool/",
    "__pycache__/",
    "migrations/",
    "vendor/",
]
HIDDEN_KEPT = {".github"}  # hidden folders worth learning from; the others hold tool or editor settings
PLAN_FOLDERS = {"plans", "specs"}  # planning documents (often written by coding assistants), not the project
BUMP_MESSAGE = re.compile(
    r"\bbump(?:ed|s)?\b|\(deps(?:-dev)?\)|dependabot|renovate|\bupdate \S+ requirement\b"
    r"|^chore\(release\)|^v?\d+\.\d+\.\d+\S*$|^version packages$",
    re.IGNORECASE,
)
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".svg", ".pdf", ".zip", ".gz", ".tar", ".7z",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".wav", ".exe", ".dll", ".so", ".dylib",
    ".pyc", ".jar", ".class", ".gguf", ".bin", ".safetensors", ".pt", ".db", ".sqlite", ".xlsx", ".docx",
}  # fmt: skip

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY"),
    re.compile(r"\bapi[_-]?key\s*[=:]", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"\b(?:secret|password|passwd|token)\s*[=:]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),  # long base64/hex runs: keys, hashes, tokens
]

LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".dart": "dart",
    ".sql": "sql",
    ".ps1": "powershell",
    ".sh": "shell",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".html": "html",
    ".ejs": "html",
    ".css": "css",
    ".scss": "css",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".scala": "scala",
    ".r": "r",
    ".kts": "kotlin",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".vue": "javascript",
    ".svelte": "javascript",
    ".bash": "shell",
    ".psm1": "powershell",
    ".lua": "lua",
    ".ex": "elixir",
    ".exs": "elixir",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
}

GENERIC_MESSAGES = {
    "wip",
    "update",
    "updates",
    "fix",
    "fixes",
    "changes",
    "misc",
    "stuff",
    "test",
    "tmp",
    "init",
}


def is_generated_path(path: str) -> bool:
    posix = PurePosixPath(path.replace("\\", "/"))
    name = posix.name
    if posix.suffix.lower() in BINARY_EXTENSIONS:
        return True
    folders = posix.parts[:-1]
    if any(part.startswith(".") and part not in HIDDEN_KEPT | {".", ".."} for part in folders):
        return True  # .venv, .dart_tool, editor and assistant settings
    if posix.suffix.lower() == ".md" and PLAN_FOLDERS.intersection(folders):
        return True
    for pattern in GENERATED_PATTERNS:
        if pattern.endswith("/"):
            if pattern[:-1] in posix.parts[:-1]:
                return True
        elif fnmatch(name, pattern):
            return True
    return False


def is_env_file(path: str) -> bool:
    name = PurePosixPath(path.replace("\\", "/")).name
    return name == ".env" or name.startswith(".env.")


def has_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def language_of(path: str) -> str | None:
    return LANGUAGES.get(PurePosixPath(path.replace("\\", "/")).suffix.lower())


def is_bump_message(message: str) -> bool:
    """Dependency bumps and release commits: they teach version-number edits, not programming."""
    return bool(BUMP_MESSAGE.search(" ".join(message.split())))


def is_trivial_message(message: str) -> bool:
    text = " ".join(message.split())
    return len(text) < 10 or text.lower() in GENERIC_MESSAGES
