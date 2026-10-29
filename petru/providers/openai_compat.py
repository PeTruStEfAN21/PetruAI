"""Streaming chat against any OpenAI-compatible server (llama-server locally)."""

from __future__ import annotations

import json
from collections.abc import Callable

from openai import DefaultHttpxClient, OpenAI

from petru.agent.cancel import Cancelled, CancelToken
from petru.providers.base import ChatResult, ToolCall


def parse_arguments(raw: str) -> dict | None:
    """JSON object from the streamed arguments; {} for none, None when unparseable."""
    if raw.strip() == "":
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


HttpPost = Callable[[str, dict, float], dict]


def _default_http_post(url: str, payload: dict, timeout: float) -> dict:
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class OpenAICompatProvider:
    def __init__(
        self,
        base_url: str,
        model: str = "local",
        client: OpenAI | None = None,
        timeout_s: float = 600.0,
        http_post: HttpPost = _default_http_post,
    ):
        self.model = model
        self.thinking = False  # /think: the model reasons first; its reasoning streams apart from the answer
        self._base_url, self._timeout_s = base_url, timeout_s
        self._server_root = base_url.rstrip("/").removesuffix("/v1")
        self._http_post = http_post
        self._client = client  # injected by tests; otherwise one client per request, so Esc can close it

    def _open(self) -> tuple[OpenAI, DefaultHttpxClient | None]:
        if self._client is not None:
            return self._client, None
        http = DefaultHttpxClient(timeout=self._timeout_s)
        return OpenAI(base_url=self._base_url, api_key="local", http_client=http), http

    def count_tokens(self, text: str) -> int | None:
        """Exact token count from llama-server's /tokenize; None when the server cannot answer."""
        try:
            tokens = self._http_post(f"{self._server_root}/tokenize", {"content": text}, 30.0).get("tokens")
        except Exception:
            return None
        return len(tokens) if isinstance(tokens, list) else None

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        on_text: Callable[[str], None] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        on_reasoning: Callable[[str], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> ChatResult:
        """One streamed reply. Cancelling `cancel` closes the connection from the cancelling thread, even
        before the first byte (a long prompt still being processed): llama-server then drops the request,
        and this raises Cancelled."""
        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": self.thinking}},
            stream_options={"include_usage": True},
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if cancel is not None:
            cancel.check()
        client, http = self._open()
        if cancel is not None:  # the loop retries a failed request itself; a retry here would outlive Esc
            client = client.with_options(max_retries=0)
        forget = cancel.on_cancel(http.close) if cancel is not None and http is not None else None
        try:
            return self._read(client.chat.completions.create(**kwargs), on_text, on_reasoning, cancel)
        except Exception as exc:
            if cancel is not None and cancel.cancelled:
                raise Cancelled from exc
            raise
        finally:
            if forget is not None:
                forget()
            if http is not None:
                http.close()

    @staticmethod
    def _read(stream, on_text, on_reasoning, cancel: CancelToken | None) -> ChatResult:
        text_parts: list[str] = []
        pending: dict[int, dict] = {}
        finish_reason = "stop"
        prompt_tokens = completion_tokens = None
        for chunk in stream:
            if cancel is not None:
                cancel.check()
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_tokens", None)
                completion_tokens = getattr(usage, "completion_tokens", None)
            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning and on_reasoning:
                        on_reasoning(reasoning)
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
