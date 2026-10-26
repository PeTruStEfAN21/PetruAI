from petru.agent.state import Phase
from petru.providers.base import ToolCall
from petru.tools.base import Tool
from petru.tui.port import ScriptedUI
from tests.fakes import FakeProvider, call, make_agent, result


def tool_names(request):
    return [t["function"]["name"] for t in request["tools"]]


def test_full_flow_design_plan_build_complete(tmp_path):
    fake = FakeProvider(
        [
            result(
                tool_calls=[call("ask_user", {"question": "Database?", "options": ["SQLite", "Postgres"]})]
            ),
            result(tool_calls=[call("plan", {"title": "Todo", "steps": ["write todo.py"]})]),
            result(tool_calls=[call("write_file", {"path": "todo.py", "content": "print('hi')\n"})]),
            result(tool_calls=[call("task_complete", {"summary": "Done"})]),
            result(content="All done."),
        ]
    )
    ui = ScriptedUI(answers=["SQLite"], plan_action="confirm")
    agent = make_agent(fake, ui, tmp_path)
    out = agent.run_turn("make a todo app")
    assert (tmp_path / "todo.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert agent.session.phase is Phase.IDLE and out == "All done."
    assert "write_file" not in tool_names(fake.calls[0])  # DESIGN phase schemas exclude writes
    assert "write_file" in tool_names(fake.calls[2])  # BUILD phase schemas include writes
    system = fake.calls[0]["messages"][0]
    assert system["role"] == "system" and "DESIGN" in system["content"]
    assert "BUILD" in fake.calls[2]["messages"][0]["content"]
    tool_msgs = [m for m in fake.calls[4]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == [
        "call_ask_user",
        "call_plan",
        "call_write_file",
        "call_task_complete",
    ]
    assert ui.questions == [("Database?", ["SQLite", "Postgres"])]
    assert ("start", "write_file", {"path": "todo.py", "content": "print('hi')\n"}) in ui.tool_events


def test_assistant_tool_call_messages_keep_openai_format(tmp_path):
    fake = FakeProvider(
        [result(content="look", tool_calls=[call("list_dir", {"path": "."})]), result(content="ok")]
    )
    make_agent(fake, ScriptedUI(), tmp_path).run_turn("x")
    assistant = fake.calls[1]["messages"][-2]
    assert assistant["role"] == "assistant" and assistant["content"] == "look"
    assert assistant["tool_calls"][0] == {
        "id": "call_list_dir",
        "type": "function",
        "function": {"name": "list_dir", "arguments": '{"path": "."}'},
    }
    tool_msg = fake.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_list_dir"


def test_write_in_design_is_denied_and_reported_to_model(tmp_path):
    fake = FakeProvider(
        [result(tool_calls=[call("write_file", {"path": "a", "content": "x"})]), result(content="ok")]
    )
    make_agent(fake, ScriptedUI(), tmp_path).run_turn("x")
    assert not (tmp_path / "a").exists()
    last = fake.calls[1]["messages"][-1]
    assert last["role"] == "tool" and "Denied" in last["content"]


def test_invalid_tool_call_retried_then_gives_up(tmp_path):
    fake = FakeProvider([result(tool_calls=[ToolCall("c", "nope", {}, "{}")])] * 3 + [result(content="x")])
    ui = ScriptedUI()
    agent = make_agent(fake, ui, tmp_path)
    agent.run_turn("x")
    assert len(fake.calls) == 3  # third invalid -> stop, no 4th request
    assert ui.notices and "invalid" in ui.notices[-1].lower()
    assert agent.stop_reason == "invalid tool calls"
    feedback = fake.calls[1]["messages"][-1]
    assert feedback["role"] == "tool" and "Invalid tool call" in feedback["content"]
    assert "read_file" in feedback["content"]  # available tools are listed


def test_invalid_arguments_are_reported_with_schema_errors(tmp_path):
    fake = FakeProvider(
        [result(tool_calls=[ToolCall("c", "read_file", {"nope": 1}, '{"nope": 1}')]), result(content="x")]
    )
    make_agent(fake, ScriptedUI(), tmp_path).run_turn("x")
    feedback = fake.calls[1]["messages"][-1]
    assert "Invalid tool call" in feedback["content"] and "path" in feedback["content"]


def test_unparseable_arguments_are_repaired(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    fake = FakeProvider(
        [result(tool_calls=[ToolCall("c", "read_file", None, "{'path': 'a.txt',}")]), result(content="x")]
    )
    make_agent(fake, ScriptedUI(), tmp_path).run_turn("x")
    assert "hello" in fake.calls[1]["messages"][-1]["content"]


def test_ask_decision_declined(tmp_path):
    fake = FakeProvider(
        [result(tool_calls=[call("shell", {"command": "npm install zod"})]), result(content="x")]
    )
    ui = ScriptedUI(confirm="no")
    agent = make_agent(fake, ui, tmp_path)
    agent.run_turn("x", quick=True)
    assert fake.calls[1]["messages"][-1]["content"] == "User declined."
    assert ui.confirms == [("Run shell {'command': 'npm install zod'}?", True)]
    assert "shell" not in agent.session.always_allow


def test_ask_decision_always(tmp_path):
    fake = FakeProvider(
        [result(tool_calls=[call("shell", {"command": "npm --version"})]), result(content="x")]
    )
    ui = ScriptedUI(confirm="always")
    agent = make_agent(fake, ui, tmp_path)
    agent.run_turn("x", quick=True)
    assert "shell" in agent.session.always_allow
    assert ("start", "shell", {"command": "npm --version"}) in ui.tool_events


def test_tool_error_is_prefixed(tmp_path):
    fake = FakeProvider(
        [result(tool_calls=[call("read_file", {"path": "missing.txt"})]), result(content="x")]
    )
    make_agent(fake, ScriptedUI(), tmp_path).run_turn("x")
    assert fake.calls[1]["messages"][-1]["content"].startswith("ERROR: ")


def test_iteration_cap(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    fake = FakeProvider(
        [result(tool_calls=[call("read_file", {"path": "a.txt"})])] * 50 + [result(content="never")]
    )
    ui = ScriptedUI()
    agent = make_agent(fake, ui, tmp_path)
    agent.run_turn("x")
    assert len(fake.calls) == 40
    assert agent.session.turn_tool_iterations == 40
    assert ui.notices and "iteration" in ui.notices[-1].lower()
    assert agent.stop_reason == "iteration limit"


def test_stop_reason_is_none_after_a_normal_turn(tmp_path):
    fake = FakeProvider([result(content="hi")])
    agent = make_agent(fake, ScriptedUI(), tmp_path)
    assert agent.run_turn("x") == "hi" and agent.stop_reason is None


class _BoomTool(Tool):
    name = "boom"
    description = "raises"
    exc: type[BaseException] = RuntimeError

    def run(self, args, ctx):
        raise self.exc("kaboom")


def test_tool_exception_is_reported_to_model_not_raised(tmp_path):
    fake = FakeProvider([result(tool_calls=[call("boom", {})]), result(content="x")])
    agent = make_agent(fake, ScriptedUI(), tmp_path)
    agent.registry.register(_BoomTool())
    agent.run_turn("x", quick=True)
    content = fake.calls[1]["messages"][-1]["content"]
    assert content.startswith("ERROR: ") and "kaboom" in content


def test_keyboard_interrupt_cancels_turn_and_keeps_transcript_valid(tmp_path):
    fake = FakeProvider([result(tool_calls=[call("boom", {})]), result(content="after")])
    ui = ScriptedUI()
    agent = make_agent(fake, ui, tmp_path)
    tool = _BoomTool()
    tool.exc = KeyboardInterrupt
    agent.registry.register(tool)
    agent.run_turn("x", quick=True)
    assert agent.stop_reason == "cancelled" and any("cancel" in n.lower() for n in ui.notices)
    assert agent.session.messages[-2]["role"] == "assistant" and agent.session.messages[-2]["tool_calls"]
    assert agent.session.messages[-1] == {
        "role": "tool",
        "tool_call_id": "call_boom",
        "content": "Cancelled by the user.",
    }
    assert agent.run_turn("go on") == "after" and agent.stop_reason is None


def test_text_fallback_tool_call_is_executed_and_stripped(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    text = 'Let me read it.\n<tool_call>{"name": "read_file", "arguments": {"path": "a.txt"}}</tool_call>'
    fake = FakeProvider([result(content=text), result(content="Final <tool_call>{}</tool_call> answer")])
    out = make_agent(fake, ScriptedUI(), tmp_path).run_turn("x")
    assert "hello" in fake.calls[1]["messages"][-1]["content"]
    assert fake.calls[1]["messages"][-2]["tool_calls"][0]["function"]["name"] == "read_file"
    assert out == "Final  answer"


def test_second_prompt_in_build_keeps_building(tmp_path):
    fake = FakeProvider(
        [
            result(tool_calls=[call("plan", {"title": "T", "steps": ["s"]})]),
            result(content="planned"),
            result(tool_calls=[call("write_file", {"path": "b.py", "content": "1\n"})]),
            result(content="written"),
        ]
    )
    agent = make_agent(fake, ScriptedUI(), tmp_path)
    agent.run_turn("make it")
    assert agent.session.phase is Phase.BUILD
    agent.run_turn("also add b.py")
    assert (tmp_path / "b.py").exists() and agent.session.phase is Phase.BUILD
    assert "Confirmed plan: T" in fake.calls[2]["messages"][0]["content"]


def test_yolo_never_asks(tmp_path):
    fake = FakeProvider(
        [result(tool_calls=[call("shell", {"command": "npm install zod"})]), result(content="x")]
    )
    ui = ScriptedUI(confirm="no")
    agent = make_agent(fake, ui, tmp_path, yolo=True)
    agent.run_turn("x")
    assert ui.confirms == [] and agent.session.phase is Phase.BUILD
    assert ("start", "shell", {"command": "npm install zod"}) in ui.tool_events


def test_compaction_runs_before_request(tmp_path):
    big = "y" * 3000
    fake = FakeProvider([result(content="summary"), result(content="done")])
    agent = make_agent(fake, ScriptedUI(), tmp_path, ctx_tokens=6000)
    agent.session.messages.extend(
        [{"role": "user", "content": big}, {"role": "assistant", "content": big}] * 3
    )
    agent.run_turn("x")
    assert any("[Summary of earlier conversation]" in m.get("content", "") for m in fake.calls[1]["messages"])
    assert fake.calls[1]["messages"][0]["role"] == "system"


class _FlakyProvider:
    def __init__(self, failures, then):
        self.failures, self.then, self.calls = failures, then, 0

    def complete(self, messages, tools, on_text=None, temperature=0.2, max_tokens=4096):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("Error code: 500 - Failed to parse tool call arguments as JSON")
        return self.then


def test_provider_error_is_retried_then_succeeds(tmp_path):
    ui = ScriptedUI()
    agent = make_agent(_FlakyProvider(2, result(content="ok")), ui, tmp_path)
    assert agent.run_turn("x") == "ok" and agent.stop_reason is None
    assert len(ui.notices) == 2 and "retry" in ui.notices[0].lower()
    assert agent.session.messages[-1] == {"role": "assistant", "content": "ok"}


def test_provider_error_gives_up_after_three(tmp_path):
    ui = ScriptedUI()
    agent = make_agent(_FlakyProvider(3, result(content="never")), ui, tmp_path)
    assert agent.run_turn("x") == "" and agent.stop_reason == "provider error"
    assert agent.session.messages[-1] == {"role": "user", "content": "x"}
