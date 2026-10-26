from petru.agent.toolcalls import extract_tool_calls, repair_json, strip_text_tool_calls, validate_arguments
from petru.providers.base import ChatResult, ToolCall

SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}},
    "required": ["path"],
    "additionalProperties": False,
}


def result(content="", tool_calls=None):
    return ChatResult(content, tool_calls or [], "stop", None, None)


def test_native_calls_win_over_text_calls():
    r = result(
        '<tool_call>{"name":"grep","arguments":{"pattern":"x"}}</tool_call>',
        [ToolCall("c1", "read_file", {"path": "a"}, '{"path":"a"}')],
    )
    assert [c.name for c in extract_tool_calls(r)] == ["read_file"]


def test_text_tag_fallback_parses_qwen_format():
    r = result('Let me search.\n<tool_call>\n{"name": "grep", "arguments": {"pattern": "x"}}\n</tool_call>')
    calls = extract_tool_calls(r)
    assert [(c.id, c.name, c.arguments) for c in calls] == [("txt-1", "grep", {"pattern": "x"})]


def test_text_tag_arguments_given_as_json_string():
    r = result('<tool_call>{"name": "grep", "arguments": "{\\"pattern\\": \\"x\\"}"}</tool_call>')
    assert extract_tool_calls(r)[0].arguments == {"pattern": "x"}


def test_json_fence_fallback_and_sequential_ids():
    r = result(
        '```json\n{"name": "list_dir", "arguments": {}}\n```\nthen\n'
        '```json\n{"name": "glob", "arguments": {"pattern": "*.py"}}\n```'
    )
    calls = extract_tool_calls(r)
    assert [(c.id, c.name) for c in calls] == [("txt-1", "list_dir"), ("txt-2", "glob")]


def test_plain_prose_yields_no_calls():
    assert extract_tool_calls(result("I will call grep with pattern x.")) == []


def test_repair_json_fixes_trailing_comma_and_single_quotes():
    assert repair_json("{'path': 'a.py',}") == {"path": "a.py"}
    assert repair_json('```json\n{"path": "a.py"}\n```') == {"path": "a.py"}
    assert repair_json('{"path": "a.py", "limit": 5,}') == {"path": "a.py", "limit": 5}
    assert repair_json("not json at all") is None
    assert repair_json("[1, 2]") is None


def test_validate_arguments_reports_missing_required_and_wrong_type():
    errs = validate_arguments(SCHEMA, {"limit": "ten"})
    assert any("path" in e for e in errs) and any("limit" in e for e in errs)
    assert validate_arguments(SCHEMA, {"path": "a.py", "limit": 3}) == []
    assert validate_arguments(SCHEMA, {"path": "a.py", "bogus": 1}) != []


def test_strip_text_tool_calls_removes_blocks_only():
    text = 'Searching now.\n<tool_call>{"name":"grep","arguments":{"pattern":"x"}}</tool_call>\nDone.'
    assert strip_text_tool_calls(text) == "Searching now.\n\nDone."
    assert strip_text_tool_calls("no calls here") == "no calls here"


def test_sanitize_arguments_strips_leaked_markup():
    from petru.agent.toolcalls import sanitize_arguments

    leaked = "Scrollable?</parameter>\n</function>\n</tool_call>\n<tool_call>\n<function=list_dir>"
    args = {
        "question": leaked,
        "options": ["yes<tool_call>", "no"],
        "timeout": 60,
        "nested": {"path": "a</parameter>"},
    }
    assert sanitize_arguments(args) == {
        "question": "Scrollable?",
        "options": ["yes", "no"],
        "timeout": 60,
        "nested": {"path": "a"},
    }
    assert sanitize_arguments({"content": "x = 1 < 2\n"}) == {"content": "x = 1 < 2\n"}


def test_repair_json_cuts_leaked_markup_of_the_next_calls():
    from petru.agent.toolcalls import repair_json

    raw = """{"question":"SQLite or PostgreSQL?</parameter>
</function>
</tool_call>
<tool_call>
<function=ask_user>
<parameter=question>"""
    assert repair_json(raw) == {"question": "SQLite or PostgreSQL?"}
    nested = """{"path": "a.ts", "content": "x</parameter>
</function>"""
    assert repair_json(nested) == {"path": "a.ts", "content": "x"}
