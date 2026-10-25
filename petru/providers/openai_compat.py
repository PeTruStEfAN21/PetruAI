"""Streaming chat against any OpenAI-compatible server (llama-server locally)."""

from __future__ import annotations

import json
from collections.abc import Callable

from openai import OpenAI

from petru.providers.base import ChatResult, ToolCall

THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}


def parse_arguments(raw: str) -> dict | None:
    """JSON object from the streamed arguments; {} for none, None when unparseable."""
    if raw.strip() == "":
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class OpenAICompatProvider:
    def __init__(
        self, base_url: str, model: str = "local", client: OpenAI | None = None, timeout_s: float = 600.0
    ):
        self.model = model
        self._client = client or OpenAI(base_url=base_url, api_key="local", timeout=timeout_s)

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        on_text: Callable[[str], None] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ChatResult:
        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=THINKING_OFF,
            stream_options={"include_usage": True},
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        stream = self._client.chat.completions.create(**kwargs)

        text_parts: list[str] = []
        pending: dict[int, dict] = {}
        finish_reason = "stop"
        prompt_tokens = completion_tokens = None
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_tokens", None)
                completion_tokens = getattr(usage, "completion_tokens", None)
            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    if delta.content:
                        text_parts.append(delta.content)
                        if on_text:
                            on_text(delta.content)
                    for tc in delta.tool_calls or []:
                        slot = pending.setdefault(tc.index, {"id": None, "name": None, "args": []})
                        if tc.id:
                            slot["id"] = tc.id
                        fn = getattr(tc, "function", None)
                        if fn is not None:
                            if fn.name:
                                slot["name"] = fn.name
                            if fn.arguments:
                                slot["args"].append(fn.arguments)
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason

        tool_calls = []
        for index in sorted(pending):
            slot = pending[index]
            raw = "".join(slot["args"])
            tool_calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{index}",
                    name=slot["name"] or "",
                    arguments=parse_arguments(raw),
                    raw_arguments=raw,
                )
            )
        return ChatResult("".join(text_parts), tool_calls, finish_reason, prompt_tokens, completion_tokens)
