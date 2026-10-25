"""Registry of available tools and their OpenAI-format schemas."""

from __future__ import annotations

from collections.abc import Iterable

from petru.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self, names: Iterable[str] | None = None) -> list[dict]:
        if names is None:
            selected = list(self._tools.values())
        else:
            selected = [self._tools[n] for n in names if n in self._tools]
        return [tool.to_openai_schema() for tool in selected]


def default_registry(ctx_online: bool) -> ToolRegistry:
    """All built-in tools. `ctx_online` reserves room for online-only tools (none yet)."""
    from petru.tools import checks, fs, git, interaction, shell

    registry = ToolRegistry()
    for tool in [*fs.TOOLS, shell.shell, git.git, checks.run_checks, *interaction.TOOLS]:
        registry.register(tool)
    return registry
