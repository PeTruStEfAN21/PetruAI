"""Filesystem tools: read, write, edit, list, glob and grep inside the project."""

from __future__ import annotations

import fnmatch
import os
import re
from collections.abc import Iterator
from pathlib import Path

from petru.tools.base import Tool, ToolContext, ToolResult
from petru.tools.paths import OutsideProjectError, resolve_in_project

IGNORED_DIRS = {".git", "node_modules", ".venv", ".dart_tool", "build", "__pycache__", "dist"}
MAX_GLOB_RESULTS = 200
MAX_GREP_FILE_BYTES = 2_000_000


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _walk_files(start: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(start):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return b"\0" in fh.read(1024)
    except OSError:
        return True


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read a UTF-8 text file from the project with line numbers. Use offset/limit for long files."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the project root"},
            "offset": {"type": "integer", "minimum": 1, "description": "First line to show (1-based)"},
            "limit": {"type": "integer", "minimum": 1, "description": "Maximum lines to show (default 400)"},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            path = resolve_in_project(args["path"], ctx.project_root)
        except OutsideProjectError as exc:
            return ToolResult(str(exc), True)
        if not path.is_file():
            return ToolResult(f"File not found: {args['path']}", True)
        offset = int(args.get("offset") or 1)
        limit = int(args.get("limit") or 400)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return ToolResult(f"Cannot read {args['path']}: {exc}", True)
        end = offset - 1 + limit
        out = [f"{offset + i}\t{line}" for i, line in enumerate(lines[offset - 1 : end])]
        if end < len(lines):
            out.append(
                f"... {len(lines) - end} more lines ({len(lines)} total). Use offset={end + 1} to continue."
            )
        return ToolResult("\n".join(out) if out else "(empty file)")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create or overwrite a UTF-8 text file inside the project. Parent folders are created."
    mutating = True
    changes_files = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the project root"},
            "content": {"type": "string", "description": "Full file content"},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            path = resolve_in_project(args["path"], ctx.project_root)
        except OutsideProjectError as exc:
            return ToolResult(str(exc), True)
        content = str(args.get("content", ""))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        except OSError as exc:
            return ToolResult(f"Cannot write {args['path']}: {exc}", True)
        return ToolResult(f"Wrote {len(content.encode('utf-8'))} bytes to {_rel(path, ctx.project_root)}")


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Replace one exact occurrence of `old` with `new` in a file. `old` must match exactly once "
        "(whitespace differences are tolerated); set replace_all to replace every occurrence."
    )
    mutating = True
    changes_files = True
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string", "description": "Text to find"},
            "new": {"type": "string", "description": "Replacement text"},
            "replace_all": {"type": "boolean", "description": "Replace every occurrence (default false)"},
        },
        "required": ["path", "old", "new"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            path = resolve_in_project(args["path"], ctx.project_root)
        except OutsideProjectError as exc:
            return ToolResult(str(exc), True)
        if not path.is_file():
            return ToolResult(f"File not found: {args['path']}", True)
        old, new = str(args["old"]), str(args["new"])
        replace_all = bool(args.get("replace_all", False))
        text = path.read_text(encoding="utf-8")
        rel = _rel(path, ctx.project_root)

        count = text.count(old) if old else 0
        if count and (count == 1 or replace_all):
            updated = text.replace(old, new)
        else:
            if count == 0 and old.split():
                pattern = r"\s+".join(re.escape(token) for token in old.split())
                matches = list(re.finditer(pattern, text))
                count = len(matches)
                if count == 1:
                    m = matches[0]
                    updated = text[: m.start()] + new + text[m.end() :]
                elif count > 1 and replace_all:
                    updated = re.sub(pattern, lambda _m: new, text)
            if count != 1 and not (count > 1 and replace_all):
                return ToolResult(
                    f"edit_file: found {count} matches for the old text in {rel}; "
                    "make it unique with more context, or set replace_all=true.",
                    True,
                )
        path.write_text(updated, encoding="utf-8", newline="\n")
        return ToolResult(f"Edited {rel}: replaced {count} occurrence{'s' if count != 1 else ''}")


class ListDirTool(Tool):
    name = "list_dir"
    description = "List the entries of a directory inside the project. Directories end with '/'."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory relative to the project root (default '.')"}
        },
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            path = resolve_in_project(args.get("path") or ".", ctx.project_root)
        except OutsideProjectError as exc:
            return ToolResult(str(exc), True)
        if not path.is_dir():
            return ToolResult(f"Not a directory: {args.get('path') or '.'}", True)
        entries = []
        for child in sorted(path.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
            if child.name in IGNORED_DIRS:
                continue
            entries.append(child.name + "/" if child.is_dir() else child.name)
        return ToolResult("\n".join(entries) if entries else "(empty directory)")


class GlobTool(Tool):
    name = "glob"
    description = "Find files by glob pattern (e.g. '**/*.py'). Returns paths relative to the project root."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "Directory to search in (default '.')"},
        },
        "required": ["pattern"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            base = resolve_in_project(args.get("path") or ".", ctx.project_root)
        except OutsideProjectError as exc:
            return ToolResult(str(exc), True)
        found = []
        for match in sorted(base.glob(args["pattern"])):
            if not match.is_file() or any(part in IGNORED_DIRS for part in match.relative_to(base).parts):
                continue
            found.append(_rel(match, ctx.project_root))
            if len(found) >= MAX_GLOB_RESULTS:
                found.append(f"... truncated at {MAX_GLOB_RESULTS} results")
                break
        return ToolResult("\n".join(found) if found else "No files match.")


class GrepTool(Tool):
    name = "grep"
    description = "Search file contents with a regular expression. Output: path:line: text."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Python regular expression"},
            "path": {"type": "string", "description": "Directory or file to search (default '.')"},
            "glob": {"type": "string", "description": "Only files whose name matches, e.g. '*.py'"},
            "max_results": {"type": "integer", "minimum": 1, "description": "Default 100"},
        },
        "required": ["pattern"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            base = resolve_in_project(args.get("path") or ".", ctx.project_root)
            regex = re.compile(args["pattern"])
        except OutsideProjectError as exc:
            return ToolResult(str(exc), True)
        except re.error as exc:
            return ToolResult(f"Invalid regular expression: {exc}", True)
        name_filter = args.get("glob")
        max_results = int(args.get("max_results") or 100)
        files = [base] if base.is_file() else _walk_files(base)
        hits: list[str] = []
        for file in files:
            if name_filter and not fnmatch.fnmatch(file.name, name_filter):
                continue
            try:
                if file.stat().st_size > MAX_GREP_FILE_BYTES or _is_binary(file):
                    continue
                lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            rel = _rel(file, ctx.project_root)
            for number, line in enumerate(lines, start=1):
                if regex.search(line):
                    hits.append(f"{rel}:{number}: {line.rstrip()}")
                    if len(hits) >= max_results:
                        hits.append(f"... truncated at {max_results} results")
                        return ToolResult("\n".join(hits))
        return ToolResult("\n".join(hits) if hits else "No matches.")


read_file = ReadFileTool()
write_file = WriteFileTool()
edit_file = EditFileTool()
list_dir = ListDirTool()
glob = GlobTool()
grep = GrepTool()
TOOLS: list[Tool] = [read_file, write_file, edit_file, list_dir, glob, grep]
