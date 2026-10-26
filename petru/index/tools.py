"""`search_code` (this project) and `search_docs` (Flutter SDK and offline docs clones) for the agent."""

from __future__ import annotations

import shutil
from pathlib import Path

from petru.index.embed_server import EMBED_URL, embed_server_healthy
from petru.index.embeddings import Embedder
from petru.index.store import CodeIndex, Hit
from petru.memory.store import petru_home
from petru.tools.base import Tool, ToolContext, ToolResult

QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "identifiers, words or a description of what you look for",
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
    },
    "required": ["query"],
    "additionalProperties": False,
}


def embedder_if_running() -> Embedder | None:
    """Vectors only when the embeddings server is already up; otherwise search falls back to BM25."""
    return Embedder(EMBED_URL) if embed_server_healthy() else None


def project_index(root: Path) -> CodeIndex:
    return CodeIndex(root / ".petru" / "index.sqlite", embedder_if_running())


def docs_index_path() -> Path:
    return petru_home() / "docs_index.sqlite"


def docs_roots(repo_root: Path) -> dict[str, Path]:
    """Offline documentation: the installed Flutter SDK's framework source and the docs clones."""
    roots: dict[str, Path] = {}
    flutter = shutil.which("flutter")
    if flutter:
        lib = Path(flutter).resolve().parent.parent / "packages" / "flutter" / "lib"
        if lib.is_dir():
            roots["flutter-sdk"] = lib
    docs = repo_root / "infra" / "offline" / "docs"
    if docs.is_dir():
        for child in sorted(docs.iterdir()):
            if child.is_dir():
                roots[child.name] = child
    return roots


def format_hits(hits: list[Hit]) -> str:
    if not hits:
        return "No matches."
    blocks = []
    for hit in hits:
        title = f"{hit.path}:{hit.start}-{hit.end} {hit.kind} {hit.name}".rstrip()
        blocks.append(f"{title}\n{hit.snippet}")
    return "\n\n".join(blocks)


class SearchCodeTool(Tool):
    name = "search_code"
    description = (
        "Search this project's code by identifier, words or meaning. Returns path:lines, the definition kind "
        "and name, and the code. Use it before reading files when you do not know where something lives."
    )
    parameters = QUERY_SCHEMA

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        index = project_index(ctx.project_root)
        try:
            index.update(ctx.project_root, backfill=False)  # keep searches fast; petru index backfills
            return ToolResult(format_hits(index.search(str(args["query"]), int(args.get("limit") or 8))))
        finally:
            index.close()


class SearchDocsTool(Tool):
    name = "search_docs"
    description = (
        "Search the offline documentation: the installed Flutter SDK source (current API) and the Flutter, "
        "Dart and samples docs. Use it for Flutter/Dart API questions instead of guessing."
    )
    parameters = QUERY_SCHEMA

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = docs_index_path()
        if not path.is_file():
            return ToolResult("The docs index was never built. Ask the user to run: petru index --docs")
        index = CodeIndex(path, embedder_if_running())
        try:
            return ToolResult(format_hits(index.search(str(args["query"]), int(args.get("limit") or 8))))
        finally:
            index.close()


TOOLS: list[Tool] = [SearchCodeTool(), SearchDocsTool()]
