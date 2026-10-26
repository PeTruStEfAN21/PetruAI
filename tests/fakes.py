"""Test doubles shared across the suite: fake OpenAI client chunks and a scripted provider."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

from petru.providers.base import ChatResult, ToolCall


def delta(content=None, tool_call=None, finish_reason=None):
    """One streaming chunk shaped like the OpenAI SDK's ChatCompletionChunk."""
    tool_calls = None
    if tool_call is not None:
        tool_calls = [
            SimpleNamespace(
                index=tool_call.get("index", 0),
                id=tool_call.get("id"),
                function=SimpleNamespace(name=tool_call.get("name"), arguments=tool_call.get("arguments")),
            )
        ]
    choice = SimpleNamespace(
        delta=SimpleNamespace(content=content, tool_calls=tool_calls), finish_reason=finish_reason
    )
    return SimpleNamespace(choices=[choice], usage=None)


def finish(reason, prompt_tokens=None, completion_tokens=None):
    usage = None
    if prompt_tokens is not None:
        usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    choice = SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=None), finish_reason=reason)
    return SimpleNamespace(choices=[choice], usage=usage)


class FakeOpenAIClient:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.last_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        return iter(self._chunks)


class FakeProvider:
    """Returns scripted ChatResults in order and records every request."""

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls: list[dict] = []

    def complete(self, messages, tools, on_text=None, temperature=0.2, max_tokens=4096):
        self.calls.append({"messages": copy.deepcopy(messages), "tools": tools})
        if not self._scripted:
            raise AssertionError("FakeProvider: no scripted result left")
        result: ChatResult = self._scripted.pop(0)
        if on_text and result.content:
            on_text(result.content)
        return result


def result(content="", tool_calls=None):
    return ChatResult(content, list(tool_calls or []))


def call(name, args, call_id=None):
    return ToolCall(call_id or f"call_{name}", name, dict(args), json.dumps(args))


def make_agent(provider, ui, root, **kwargs):
    from petru.agent.loop import Agent
    from petru.agent.state import Session
    from petru.tools.registry import default_registry

    session = Session(root, yolo=kwargs.pop("yolo", False))
    return Agent(
        provider=provider,
        registry=default_registry(ctx_online=False),
        ui=ui,
        session=session,
        repo_root=root,
        ctx_tokens=kwargs.pop("ctx_tokens", 16384),
        online=False,
        **kwargs,
    )
