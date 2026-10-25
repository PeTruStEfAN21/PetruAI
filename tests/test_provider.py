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
