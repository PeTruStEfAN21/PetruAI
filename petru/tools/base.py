"""Tool protocol shared by every plugin."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ToolResult:
    output: str
    is_error: bool = False


@dataclass
class ToolContext:
    project_root: Path
    online: bool
    ui: Any = None  # UIPort, defined in petru.tui.port
    session: Any = None  # Session, defined in petru.agent.state


class Tool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict = {"type": "object", "properties": {}}
    mutating: bool = False
    changes_files: bool = False  # its success leaves the project unverified until run_checks is green

    @abstractmethod
    def run(self, args: dict, ctx: ToolContext) -> ToolResult: ...

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }
