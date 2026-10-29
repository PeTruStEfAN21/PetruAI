from petru.agent.state import Phase
from petru.providers.base import ToolCall
from petru.tools.base import Tool, ToolResult
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
    reads = [result(tool_calls=[call("read_file", {"path": "a.txt", "offset": i + 1})]) for i in range(50)]
    fake = FakeProvider(reads + [result(content="never")])  # different calls: no repeat stops it first
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

    def complete(self, messages, tools, on_text=None, temperature=0.2, max_tokens=4096, **kwargs):
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


class _RecordingFlaky(_FlakyProvider):
    temperatures: list[float] = []

    def complete(self, messages, tools, on_text=None, temperature=0.2, max_tokens=4096, **kwargs):
        self.temperatures.append(temperature)
        return super().complete(messages, tools, on_text, temperature, max_tokens)


def test_provider_retry_raises_temperature(tmp_path):
    provider = _RecordingFlaky(2, result(content="ok"))
    provider.temperatures = []
    make_agent(provider, ScriptedUI(), tmp_path).run_turn("x")
    assert provider.temperatures == [0.2, 0.5, 0.8]


def test_repaired_tool_calls_are_recorded_in_canonical_form(tmp_path):
    import json

    raw = """{"question": "SQLite or Postgres?</parameter>
</function>
<tool_call>"""
    broken = ToolCall("c1", "ask_user", None, raw)
    fake = FakeProvider([result(tool_calls=[broken]), result(content="ok")])
    agent = make_agent(fake, ScriptedUI(answers=["SQLite"]), tmp_path)
    agent.run_turn("make a todo app")
    recorded = agent.session.messages[-3]["tool_calls"][0]["function"]["arguments"]
    assert json.loads(recorded) == {"question": "SQLite or Postgres?"} and "<" not in recorded
    assert agent.session.messages[-2]["content"] == "SQLite"


class _FloodTool(Tool):
    name = "flood"
    description = "returns a huge output"

    def run(self, args, ctx):
        from petru.tools.base import ToolResult

        return ToolResult("HEAD" + "x" * 200_000 + "TAIL")


def test_a_huge_tool_result_is_cut_before_it_reaches_the_model(tmp_path):
    from petru.agent.loop import MAX_TOOL_RESULT_CHARS

    fake = FakeProvider([result(tool_calls=[call("flood", {})]), result(content="x")])
    agent = make_agent(fake, ScriptedUI(), tmp_path)
    agent.registry.register(_FloodTool())
    agent.run_turn("x", quick=True)
    content = fake.calls[1]["messages"][-1]["content"]
    assert (
        len(content) < MAX_TOOL_RESULT_CHARS + 200 and content.startswith("HEAD") and content.endswith("TAIL")
    )
    assert "truncated" in content


def test_unparseable_arguments_never_reach_the_server_again(tmp_path):
    import json

    broken = ToolCall("c1", "ask_user", None, "<<not json at all")
    fake = FakeProvider([result(tool_calls=[broken]), result(content="ok")])
    agent = make_agent(fake, ScriptedUI(), tmp_path)
    agent.run_turn("x")
    history = fake.calls[1]["messages"]
    recorded = history[-2]["tool_calls"][0]["function"]["arguments"]
    assert (
        json.loads(recorded) == {}
    )  # llama-server answers 500 to every request whose history has invalid JSON
    assert "not a JSON object" in history[-1]["content"]


def test_design_stops_offering_ask_user_after_two_turned_away_questions(tmp_path):
    same = {"question": "Same?"}
    fake = FakeProvider(
        [
            result(tool_calls=[call("ask_user", same, "c1")]),
            result(tool_calls=[call("ask_user", same, "c2")]),
            result(tool_calls=[call("ask_user", same, "c3")]),
            result(tool_calls=[call("plan", {"title": "T", "steps": ["a"]}, "c4")]),
            result(tool_calls=[call("task_complete", {"summary": "done"}, "c5")]),
            result(content="ok"),
        ]
    )
    ui = ScriptedUI(answers=["A"], plan_action="confirm")
    agent = make_agent(fake, ui, tmp_path)
    assert agent.run_turn("make it") == "ok"
    assert "ask_user" in tool_names(fake.calls[2]) and "ask_user" not in tool_names(fake.calls[3])
    assert len(ui.questions) == 1 and agent.session.turned_away_questions == 0  # reset when the task closed


def test_unparseable_arguments_tell_the_model_where_the_json_broke(tmp_path):
    broken = ToolCall("c1", "shell", None, '{"command": "python -c "print(1)""}')
    fake = FakeProvider([result(tool_calls=[broken]), result(content="ok")])
    agent = make_agent(fake, ScriptedUI(), tmp_path)
    agent.run_turn("x")
    content = fake.calls[1]["messages"][-1]["content"]
    assert "line 1 column 25" in content and 'python -c "print(1)' in content
    assert "write_file" in content  # long code goes in a file instead


def test_a_large_context_gives_the_model_room_for_a_whole_file(tmp_path):
    fake = FakeProvider([result(content="ok"), result(content="ok")])
    make_agent(fake, ScriptedUI(), tmp_path, ctx_tokens=32768).run_turn("x", quick=True)
    make_agent(fake, ScriptedUI(), tmp_path, ctx_tokens=8192).run_turn("x", quick=True)
    assert [c["max_tokens"] for c in fake.calls] == [8192, 4096]


def test_a_call_cut_off_at_the_output_limit_is_told_to_write_in_parts(tmp_path):
    from petru.providers.base import ChatResult

    broken = ToolCall("c1", "write_file", None, '{"path": "big.py", "content": "def f():')
    fake = FakeProvider([ChatResult("", [broken], "length"), result(content="ok")])
    make_agent(fake, ScriptedUI(), tmp_path).run_turn("x")
    content = fake.calls[1]["messages"][-1]["content"]
    assert "cut off" in content and "append" in content


def read_a(i):
    return result(tool_calls=[call("read_file", {"path": "a.py"}, f"c{i}")])


def test_a_call_repeated_with_nothing_changed_is_pointed_out(tmp_path):
    # a lead once ran the same failing checks every few seconds for 90 minutes without changing a file
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    fake = FakeProvider([read_a(1), read_a(2), result(content="ok")])
    make_agent(fake, ScriptedUI(), tmp_path, yolo=True).run_turn("x")
    first, second = (fake.calls[i]["messages"][-1]["content"] for i in (1, 2))
    assert "x = 1" in first and "x = 1" in second
    assert "nothing changed" not in first and "nothing changed" in second


def test_a_change_in_between_makes_a_repeated_call_new(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    write = result(tool_calls=[call("write_file", {"path": "b.py", "content": "y = 2\n"})])
    fake = FakeProvider([read_a(1), write, read_a(2), result(content="ok")])
    make_agent(fake, ScriptedUI(), tmp_path, yolo=True).run_turn("x")
    assert "nothing changed" not in fake.calls[3]["messages"][-1]["content"]


def test_repeating_without_progress_ends_the_turn(tmp_path):
    from petru.agent.loop import REPEAT_LIMIT

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    fake = FakeProvider([read_a(i) for i in range(REPEAT_LIMIT + 5)] + [result(content="ok")])
    ui = ScriptedUI()
    agent = make_agent(fake, ui, tmp_path, yolo=True)
    agent.run_turn("x")
    assert agent.stop_reason == "no progress" and len(fake.calls) == REPEAT_LIMIT + 1
    assert "no file changed" in ui.notices[-1]


class _ChecksTool(Tool):
    name = "checks"
    description = "fails the same way, each run with its own duration"

    def __init__(self):
        self.runs = 0

    def run(self, args, ctx):
        from petru.tools.base import ToolResult

        self.runs += 1
        return ToolResult(
            f"ImportError: no module tracker.query\n1 error in 0.{self.runs}9s (0:00:0{self.runs})", True
        )


def test_a_run_that_differs_only_in_its_duration_is_the_same_result(tmp_path):
    checks = [result(tool_calls=[call("checks", {}, f"c{i}")]) for i in range(2)]
    fake = FakeProvider([*checks, result(content="ok")])
    agent = make_agent(fake, ScriptedUI(), tmp_path, yolo=True)
    agent.registry.register(_ChecksTool())
    agent.run_turn("x")
    assert "nothing changed" in fake.calls[2]["messages"][-1]["content"]


def test_a_turn_past_its_deadline_stops_on_its_own(tmp_path):
    import time

    fake = FakeProvider([result(content="never")])
    ui = ScriptedUI()
    agent = make_agent(fake, ui, tmp_path, deadline=time.monotonic() - 1)
    agent.run_turn("x")
    assert agent.stop_reason == "time limit" and not fake.calls
    assert "time" in ui.notices[-1].lower()


def test_a_message_typed_during_the_turn_reaches_the_model_at_the_next_step(tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    fake = FakeProvider([result(tool_calls=[call("read_file", {"path": "a.txt"})]), result(content="ok")])
    ui = ScriptedUI(interjections=["why pytest?"])
    agent = make_agent(fake, ui, tmp_path)
    agent.run_turn("x", quick=True)
    last = fake.calls[1]["messages"][-2:]
    assert last[0]["role"] == "tool" and last[1] == {"role": "user", "content": "why pytest?"}
    assert ui.take_messages() == []


class _EscOnFirstReply(FakeProvider):
    def complete(self, messages, tools, on_text=None, temperature=0.2, max_tokens=4096, **kwargs):
        if not self.calls:
            self.calls.append({"messages": messages})
            from petru.agent.cancel import Cancelled

            raise Cancelled
        return super().complete(messages, tools, on_text, temperature, max_tokens, **kwargs)


def test_esc_during_a_model_reply_stops_the_turn_cleanly(tmp_path):
    ui = ScriptedUI()
    agent = make_agent(_EscOnFirstReply([result(content="after")]), ui, tmp_path)
    agent.run_turn("x", quick=True)
    assert agent.stop_reason == "cancelled" and "Turn cancelled." in ui.notices
    assert agent.session.messages[-1]["role"] == "user"  # nothing half-recorded
    agent.cancel.cancel()  # a stale Esc from before the next prompt must not stop it
    assert agent.run_turn("again") == "after" and agent.stop_reason is None


class _EscTool(Tool):
    name = "esc"
    description = "presses Esc while it runs"

    def __init__(self, agent):
        self.agent = agent

    def run(self, args, ctx):
        self.agent.cancel.cancel()
        return ToolResult("done", False)


def test_esc_between_calls_marks_the_rest_cancelled(tmp_path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    calls = [call("esc", {}), call("read_file", {"path": "a.txt"})]
    agent = make_agent(FakeProvider([result(tool_calls=calls)]), ScriptedUI(), tmp_path)
    agent.registry.register(_EscTool(agent))
    agent.run_turn("x", quick=True)
    tools = [m["content"] for m in agent.session.messages if m["role"] == "tool"]
    assert tools == ["done", "Cancelled by the user."] and agent.stop_reason == "cancelled"


class _Thinking(FakeProvider):
    def complete(self, messages, tools, on_text=None, temperature=0.2, max_tokens=4096, **kwargs):
        kwargs["on_reasoning"]("thinking")
        return super().complete(messages, tools, on_text, temperature, max_tokens, **kwargs)


def test_reasoning_goes_to_the_ui(tmp_path):
    ui = ScriptedUI()
    make_agent(_Thinking([result(content="ok")]), ui, tmp_path).run_turn("x", quick=True)
    assert ui.reasonings == ["thinking"]
