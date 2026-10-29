"""Provider-neutral chat types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from petru.agent.cancel import CancelToken


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict | None
    raw_arguments: str


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatProvider(Protocol):
    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        on_text: Callable[[str], None] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        on_reasoning: Callable[[str], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> ChatResult: ...
