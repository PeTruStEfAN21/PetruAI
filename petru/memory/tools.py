"""`remember` and `recall`: the agent's own long-term notes, plus the memory section of the system prompt."""

from __future__ import annotations

import re
from pathlib import Path

from petru.memory.store import MEMORY_TYPES, MemoryStore, memory_dir
from petru.tools.base import Tool, ToolContext, ToolResult

_SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY|\bsk-[A-Za-z0-9]{20,}"
    r"|\b(?:api[_-]?key|secret|password|passwd|token)\s*[=:]",
    re.IGNORECASE,
)
SCOPE_SCHEMA = {"type": "string", "enum": ["project", "global"], "description": "project (default) or global"}


def _store(scope: str, ctx: ToolContext) -> MemoryStore:
    return MemoryStore(memory_dir("global" if scope == "global" else "project", ctx.project_root))


class RememberTool(Tool):
    name = "remember"
    description = (
        "Save a durable fact for future sessions: a user preference (type user), a correction or working "
        "rule (feedback), a project fact not visible in the code (project) or a pointer to an external "
        "resource (reference). Same name again adds to it. Use scope global for things true in every "
        "project. Never store secrets."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short title, reused to add to the same memory"},
            "description": {"type": "string", "description": "One line shown in the memory index"},
            "type": {"type": "string", "enum": list(MEMORY_TYPES)},
            "content": {"type": "string"},
            "scope": SCOPE_SCHEMA,
        },
        "required": ["name", "description", "type", "content"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if _SECRET.search(str(args.get("content", ""))):
            return ToolResult("Refused: the content looks like a secret (key, token or password).", True)
        scope = str(args.get("scope") or "project")
        try:
            memory = _store(scope, ctx).remember(
                str(args["name"]), str(args["description"]), str(args["type"]), str(args["content"])
            )
        except ValueError as exc:
            return ToolResult(str(exc), True)
        return ToolResult(f"Remembered {memory.name!r} ({scope} memory, {memory.type}).")


class RecallTool(Tool):
    name = "recall"
    description = "Read one memory listed in the memory index, by its name."
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "scope": SCOPE_SCHEMA},
        "required": ["name"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        scope = str(args.get("scope") or "project")
        memory = _store(scope, ctx).get(str(args["name"]))
        if memory is None and "scope" not in args:
            scope, memory = "global", _store("global", ctx).get(str(args["name"]))
        if memory is None:
            return ToolResult(f"No memory named {args['name']!r} in {scope} memory.")
        return ToolResult(f"{memory.name} ({memory.type}): {memory.description}\n\n{memory.body}")


def memory_prompt_section(project_root: Path, max_tokens: int = 1500) -> str:
    """Global then project memory indexes; the oldest project lines go first when over budget."""
    global_lines = MemoryStore(memory_dir("global", project_root)).index_text().splitlines()
    project_lines = MemoryStore(memory_dir("project", project_root)).index_text().splitlines()

    def render() -> str:
        parts = []
        if global_lines:
            parts.append("## Memory (global)\n" + "\n".join(global_lines))
        if project_lines:
            parts.append("## Memory (project)\n" + "\n".join(project_lines))
        if parts:
            parts.append("Use recall to read a memory; use remember to save durable facts.")
        return "\n\n".join(parts)

    text = render()
    while len(text) // 4 > max_tokens and (project_lines or global_lines):
        (project_lines if project_lines else global_lines).pop(0)
        text = render()
    return text


TOOLS: list[Tool] = [RememberTool(), RecallTool()]
