"""Split source files into searchable chunks: one per definition (tree-sitter), windows for the rest."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from petru.tools.fs import IGNORED_DIRS

MAX_FILE_BYTES = 200_000
WINDOW, OVERLAP = 60, 10
MAX_CHUNK_LINES = 200

LANGUAGE_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".dart": "dart", ".go": "go", ".rs": "rust", ".java": "java",
    ".cs": "csharp", ".kt": "kotlin", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".sql": "sql", ".sh": "bash", ".ps1": "powershell", ".md": "markdown", ".html": "html", ".css": "css",
}  # fmt: skip

_JS = {
    "class_declaration": "class", "abstract_class_declaration": "class", "function_declaration": "function",
    "generator_function_declaration": "function", "method_definition": "function",
    "interface_declaration": "type", "type_alias_declaration": "type", "enum_declaration": "type",
}  # fmt: skip
DEFINITIONS: dict[str, dict[str, str]] = {
    "python": {"class_definition": "class", "function_definition": "function"},
    "javascript": _JS,
    "typescript": _JS,
    "tsx": _JS,
    "dart": {
        "class_definition": "class",
        "mixin_declaration": "class",
        "extension_declaration": "class",
        "enum_declaration": "type",
        "function_signature": "function",
        "method_signature": "function",
    },  # fmt: skip
    "go": {"function_declaration": "function", "method_declaration": "function", "type_declaration": "type"},
    "rust": {
        "function_item": "function",
        "impl_item": "class",
        "struct_item": "type",
        "enum_item": "type",
        "trait_item": "type",
    },  # fmt: skip
    "java": {
        "class_declaration": "class",
        "interface_declaration": "type",
        "enum_declaration": "type",
        "method_declaration": "function",
        "constructor_declaration": "function",
    },  # fmt: skip
    "csharp": {
        "class_declaration": "class",
        "interface_declaration": "type",
        "struct_declaration": "type",
        "enum_declaration": "type",
        "method_declaration": "function",
        "constructor_declaration": "function",
    },  # fmt: skip
    "kotlin": {
        "class_declaration": "class",
        "object_declaration": "class",
        "function_declaration": "function",
    },
    "c": {"function_definition": "function", "struct_specifier": "type"},
    "cpp": {"function_definition": "function", "class_specifier": "class", "struct_specifier": "type"},
}
_FUNCTION_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}
_NAME_TYPES = {
    "identifier",
    "type_identifier",
    "property_identifier",
    "field_identifier",
    "simple_identifier",
}


@dataclass
class Chunk:
    path: str
    start: int  # 1-based, inclusive
    end: int
    kind: str  # class | function | type | window
    name: str
    text: str


def _name(node) -> str:
    for field in ("name", "declarator", "type"):
        child = node.child_by_field_name(field)
        if child is not None:
            if child.type in _NAME_TYPES:
                return child.text.decode("utf-8", errors="replace")
            nested = _name(child)
            if nested:
                return nested
    for child in node.named_children:
        if child.type in _NAME_TYPES:
            return child.text.decode("utf-8", errors="replace")
    return ""


def _definitions(root, language: str) -> list[tuple[int, int, str, str]]:
    """(start_line, end_line, kind, name) for every definition, nested ones included."""
    kinds = DEFINITIONS.get(language, {})
    found: list[tuple[int, int, str, str]] = []

    def visit(node) -> None:
        kind = kinds.get(node.type)
        if (
            node.type == "function_signature"
            and node.parent is not None
            and node.parent.type == "method_signature"
        ):
            kind = None  # Dart: the method_signature around it is the definition
        if kind is not None:
            end = node.end_point[0]
            sibling = node.next_named_sibling
            if node.type in ("function_signature", "method_signature") and sibling is not None:
                if sibling.type == "function_body":
                    end = sibling.end_point[0]  # Dart keeps the body as a sibling of the signature
            name = _name(node)
            if not name and node.type == "method_signature":
                inner = next((c for c in node.named_children if c.type == "function_signature"), None)
                name = _name(inner) if inner is not None else ""
            found.append((node.start_point[0] + 1, end + 1, kind, name))
        elif node.type in ("lexical_declaration", "variable_declaration"):
            for declarator in node.named_children:
                value = declarator.child_by_field_name("value")
                if value is not None and value.type in _FUNCTION_VALUES:
                    found.append(
                        (node.start_point[0] + 1, node.end_point[0] + 1, "function", _name(declarator))
                    )
        for child in node.named_children:
            visit(child)

    visit(root)
    return found


def _windows(path: str, lines: list[str], first: int, last: int) -> list[Chunk]:
    """Overlapping windows over lines first..last (1-based, inclusive)."""
    chunks, start = [], first
    while start <= last:
        end = min(start + WINDOW - 1, last)
        chunks.append(Chunk(path, start, end, "window", "", "\n".join(lines[start - 1 : end])))
        if end == last:
            break
        start = end - OVERLAP + 1
    return chunks


def _uncovered_runs(lines: list[str], covered: set[int]) -> list[tuple[int, int]]:
    runs, start = [], None
    for number in range(1, len(lines) + 2):
        free = number <= len(lines) and number not in covered
        if free and start is None:
            start = number
        elif not free and start is not None:
            body = [i for i in range(start, number) if lines[i - 1].strip()]
            if len(body) >= 3:
                runs.append((body[0], body[-1]))
            start = None
    return runs


def chunk_file(path: str, text: str) -> list[Chunk]:
    lines = text.splitlines()
    if not any(line.strip() for line in lines):
        return []
    language = LANGUAGE_BY_EXT.get(PurePosixPath(path.replace("\\", "/")).suffix.lower())
    definitions: list[tuple[int, int, str, str]] = []
    if language in DEFINITIONS:
        try:
            from tree_sitter_language_pack import get_parser

            tree = get_parser(language).parse(text.encode("utf-8"))
            definitions = _definitions(tree.root_node, language)
        except Exception:  # grammar missing offline, parse failure: windows still make the file searchable
            definitions = []
    if not definitions:
        return _windows(path, lines, 1, len(lines))
    chunks = [
        Chunk(
            path, start, end, kind, name, "\n".join(lines[start - 1 : min(end, start + MAX_CHUNK_LINES - 1)])
        )
        for start, end, kind, name in definitions
    ]
    covered = {line for start, end, _, _ in definitions for line in range(start, end + 1)}
    for first, last in _uncovered_runs(lines, covered):
        chunks.extend(_windows(path, lines, first, last))
    return sorted(chunks, key=lambda c: (c.start, -c.end))


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return b"\x00" in fh.read(8192)
    except OSError:
        return True


SECRET_NAMES = {".npmrc", ".pypirc", ".netrc", "credentials.json", "secrets.toml", "secrets.json"}
SECRET_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")


def is_secret_file(rel: str) -> bool:
    """Files that hold credentials: they never go into an index, a journal or an export."""
    name = PurePosixPath(rel.replace("\\", "/")).name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name.startswith("id_rsa")
        or name.startswith("id_ed25519")
        or name.startswith("id_ecdsa")
        or name in SECRET_NAMES
        or name.endswith(SECRET_SUFFIXES)
    )


def _ignored(rel: str) -> bool:
    return any(part in IGNORED_DIRS for part in PurePosixPath(rel).parts[:-1]) or is_secret_file(rel)


def iter_project_files(root: Path) -> Iterator[Path]:
    """Indexable text files: git's view (tracked + untracked, minus ignored) in a repo, else a walk."""
    rels: list[str] = []
    if (root / ".git").exists():
        proc = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(root), capture_output=True, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )  # fmt: skip
        if proc.returncode == 0:
            rels = [line for line in proc.stdout.splitlines() if line]
    if not rels:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and d != ".petru")
            for filename in filenames:
                rels.append(Path(dirpath, filename).relative_to(root).as_posix())
    for rel in sorted(set(rels)):
        if _ignored(rel) or rel.startswith(".petru/"):
            continue
        path = root / rel
        if path.is_file() and path.stat().st_size <= MAX_FILE_BYTES and not _is_binary(path):
            yield path
