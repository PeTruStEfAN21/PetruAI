from petru.providers.base import ChatResult
from petru.providers.openai_compat import OpenAICompatProvider
from tests.fakes import FakeOpenAIClient, FakeProvider, delta, finish

USER = [{"role": "user", "content": "hi"}]


def make(chunks):
    client = FakeOpenAIClient(chunks)
    return OpenAICompatProvider("http://x/v1", client=client), client


def test_streams_text_and_accumulates_tool_call_arguments():
    chunks = [
        delta(content="Hel"),
        delta(content="lo"),
        delta(tool_call=dict(index=0, id="c1", name="read_file", arguments='{"pa')),
        delta(tool_call=dict(index=0, arguments='th": "a.py"}')),
        finish("tool_calls"),
    ]
    seen = []
    p, _ = make(chunks)
    r = p.complete(USER, tools=[], on_text=seen.append)
    assert "".join(seen) == "Hello" and r.content == "Hello"
    assert r.tool_calls[0].id == "c1" and r.tool_calls[0].name == "read_file"
    assert r.tool_calls[0].arguments == {"path": "a.py"}
    assert r.tool_calls[0].raw_arguments == '{"path": "a.py"}'
    assert r.finish_reason == "tool_calls"


def test_two_tool_calls_accumulate_by_index():
    chunks = [
        delta(tool_call=dict(index=0, id="a", name="grep", arguments='{"pattern":')),
        delta(tool_call=dict(index=1, id="b", name="glob", arguments='{"pattern": "*.py"}')),
        delta(tool_call=dict(index=0, arguments=' "x"}')),
        finish("tool_calls"),
    ]
    r = make(chunks)[0].complete(USER, tools=[])
    assert [(c.id, c.name, c.arguments) for c in r.tool_calls] == [
        ("a", "grep", {"pattern": "x"}),
        ("b", "glob", {"pattern": "*.py"}),
    ]


def test_invalid_json_arguments_kept_raw():
    chunks = [
        delta(tool_call=dict(index=0, id="c1", name="read_file", arguments='{"path": a.py}')),
        finish("tool_calls"),
    ]
    r = make(chunks)[0].complete(USER, tools=[])
    assert r.tool_calls[0].arguments is None and r.tool_calls[0].raw_arguments == '{"path": a.py}'


def test_empty_arguments_become_empty_dict():
    chunks = [delta(tool_call=dict(index=0, id="c1", name="list_dir", arguments="")), finish("tool_calls")]
    r = make(chunks)[0].complete(USER, tools=[])
    assert r.tool_calls[0].arguments == {}


def test_request_disables_thinking_and_streams():
    p, client = make([finish("stop", prompt_tokens=12, completion_tokens=3)])
    r = p.complete([{"role": "user", "content": "x"}], tools=None)
    kw = client.last_kwargs
    assert kw["stream"] is True
    assert kw["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert "tools" not in kw and "tool_choice" not in kw
    assert kw["messages"] == [{"role": "user", "content": "x"}]
    assert r.prompt_tokens == 12 and r.completion_tokens == 3 and r.finish_reason == "stop"


def test_tools_sent_with_auto_choice():
    tools = [
        {"type": "function", "function": {"name": "t", "parameters": {"type": "object", "properties": {}}}}
    ]
    p, client = make([finish("stop")])
    p.complete(USER, tools=tools)
    assert client.last_kwargs["tools"] == tools and client.last_kwargs["tool_choice"] == "auto"


def test_fake_provider_records_calls_and_streams_text():
    fake = FakeProvider([ChatResult("done", [], "stop", None, None)])
    seen = []
    r = fake.complete(USER, tools=None, on_text=seen.append)
    assert r.content == "done" and seen == ["done"]
    assert fake.calls[0]["messages"] == USER and fake.calls[0]["tools"] is None


def test_thinking_sends_enable_thinking_and_streams_reasoning_apart():
    p, client = make([delta(reasoning="hmm"), delta(content="answer"), finish("stop")])
    p.thinking = True
    thoughts = []
    r = p.complete(USER, tools=None, on_reasoning=thoughts.append)
    assert client.last_kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}
    assert thoughts == ["hmm"] and r.content == "answer"


class _SlowServer:
    """A local OpenAI-compatible endpoint, slow on purpose: `delay` seconds before its headers, then one SSE
    chunk every `every` seconds. It records when it noticed the client went away."""

    def __init__(self, delay: float, every: float):
        import http.server
        import threading

        outer = self
        self.received, self.closed = threading.Event(), threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _gone(self) -> bool:
                import select
                import socket

                readable, _, _ = select.select([self.connection], [], [], 0)
                if not readable:
                    return False
                try:
                    return self.connection.recv(1, socket.MSG_PEEK) == b""
                except OSError:
                    return True

            def do_POST(self):
                import json
                import time

                self.rfile.read(int(self.headers["Content-Length"]))
                outer.received.set()
                end = time.monotonic() + delay
                while time.monotonic() < end:
                    if self._gone():
                        outer.closed.set()
                        return
                    time.sleep(0.05)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for i in range(40):
                        chunk = {"choices": [{"index": 0, "delta": {"content": f"t{i} "}}]}
                        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(every)
                        if self._gone():
                            raise ConnectionAbortedError
                except OSError:
                    outer.closed.set()

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def stop(self):
        self.server.shutdown()


def _cancel_after(server, wait_for, timeout=1.5):
    """Run complete() in a thread, cancel once `wait_for(seen)` holds; returns (error, seconds to stop)."""
    import threading
    import time

    from petru.agent.cancel import CancelToken

    token, seen, outcome = CancelToken(), [], {}
    provider = OpenAICompatProvider(server.url)

    def run():
        try:
            provider.complete(USER, tools=None, on_text=seen.append, cancel=token)
        except BaseException as exc:  # noqa: BLE001 - the test inspects what came out
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not wait_for(seen) and time.monotonic() < deadline:
        time.sleep(0.02)
    started = time.monotonic()
    token.cancel()
    thread.join(timeout)
    return outcome.get("error"), time.monotonic() - started, thread.is_alive()


def test_cancel_before_the_first_byte_stops_within_a_second():
    from petru.agent.cancel import Cancelled

    server = _SlowServer(delay=10, every=0.5)
    try:
        error, took, alive = _cancel_after(server, lambda seen: server.received.is_set())
        assert not alive and isinstance(error, Cancelled)
        assert took < 0.3  # at once: a retry inside the SDK would first wait ~0.5 s
        assert server.closed.wait(3), "the server never saw the connection close"
    finally:
        server.stop()


def test_cancel_mid_stream_stops_within_a_second():
    from petru.agent.cancel import Cancelled

    server = _SlowServer(delay=0, every=0.5)
    try:
        error, took, alive = _cancel_after(server, lambda seen: bool(seen))
        assert not alive and isinstance(error, Cancelled) and took < 1.5
        assert server.closed.wait(3), "the server never saw the connection close"
    finally:
        server.stop()
