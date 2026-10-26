from petru.agent.decisions import append_decisions, read_decisions
from petru.agent.state import Phase, Session
from petru.tools.base import ToolContext, ToolResult
from petru.tools.interaction import AskUserTool, PlanTool, TaskCompleteTool
from petru.tools.registry import default_registry
from petru.tui.port import ScriptedUI


def make(root, ui, quick=False):
    s = Session(root)
    s.start_turn("app", quick=quick)
    return s, ToolContext(root, False, ui, s)


def decisions_file(root):
    return (root / ".petru" / "DECISIONS.md").read_text(encoding="utf-8")


def test_ask_user_records_answer_as_pending_decision(tmp_path):
    ui = ScriptedUI(answers=["SQLite"])
    s, ctx = make(tmp_path, ui)
    r = AskUserTool().run({"question": "Which database?", "options": ["SQLite", "Postgres"]}, ctx)
    assert r.output == "SQLite" and not r.is_error
    assert s.pending_decisions == ["Which database? -> SQLite"]
    assert ui.questions == [("Which database?", ["SQLite", "Postgres"])]
    assert not (tmp_path / ".petru").exists()


def test_ask_user_in_build_phase_is_written_immediately(tmp_path):
    ui = ScriptedUI(answers=["yes, keep it"])
    s, ctx = make(tmp_path, ui, quick=True)
    AskUserTool().run({"question": "Keep the old API?"}, ctx)
    assert "Keep the old API? -> yes, keep it" in decisions_file(tmp_path)
    assert s.pending_decisions == []


def test_ask_user_without_ui_is_error(tmp_path):
    s = Session(tmp_path)
    r = AskUserTool().run({"question": "x"}, ToolContext(tmp_path, False, None, s))
    assert r.is_error


def test_plan_confirm_moves_to_build_and_appends_decisions(tmp_path):
    ui = ScriptedUI(plan_action="confirm")
    s, ctx = make(tmp_path, ui)
    s.pending_decisions = ["db -> SQLite"]
    r = PlanTool().run(
        {"title": "Todo app", "steps": ["create cli.py", "add tests"], "decisions": ["tests -> pytest"]}, ctx
    )
    assert s.phase is Phase.BUILD and s.plan.confirmed and "BUILD" in r.output
    assert s.plan.decisions == ["db -> SQLite", "tests -> pytest"] and s.pending_decisions == []
    text = decisions_file(tmp_path)
    assert "db -> SQLite" in text and "tests -> pytest" in text and "Todo app" in text
    assert ui.plans[0].title == "Todo app"


def test_plan_edit_applies_user_changes_then_builds(tmp_path):
    ui = ScriptedUI(plan_action="edit", edited_steps=["only create cli.py"])
    s, ctx = make(tmp_path, ui)
    r = PlanTool().run({"title": "T", "steps": ["a", "b"]}, ctx)
    assert s.phase is Phase.BUILD and s.plan.steps == ["only create cli.py"]
    assert "edited" in r.output.lower() and "only create cli.py" in r.output


def test_plan_reject_stays_in_design(tmp_path):
    ui = ScriptedUI(plan_action="reject")
    s, ctx = make(tmp_path, ui)
    r = PlanTool().run({"title": "T", "steps": ["a"]}, ctx)
    assert r.is_error and "rejected" in r.output.lower()
    assert s.phase is Phase.DESIGN and s.plan is None


def test_plan_without_ui_is_error(tmp_path):
    s = Session(tmp_path)
    s.start_turn("x")
    r = PlanTool().run({"title": "T", "steps": ["a"]}, ToolContext(tmp_path, False, None, s))
    assert r.is_error and s.phase is Phase.DESIGN


def test_decisions_are_append_only_and_latest_last(tmp_path):
    append_decisions(tmp_path, ["db -> SQLite"])
    append_decisions(tmp_path, ["db -> Postgres"])
    txt = read_decisions(tmp_path)
    assert txt.index("SQLite") < txt.index("Postgres") and txt.count("- 20") == 2
    full = decisions_file(tmp_path)
    assert full.startswith("# Decizii") and full.count("# Decizii") == 1


def test_read_decisions_tail_and_missing(tmp_path):
    assert read_decisions(tmp_path) == ""
    append_decisions(tmp_path, [f"decision number {i}" for i in range(100)])
    lines = read_decisions(tmp_path, max_lines=10).splitlines()
    assert (
        len(lines) == 10
        and lines[-1].endswith("decision number 99")
        and lines[0].endswith("decision number 90")
    )


def test_task_complete_returns_to_idle(tmp_path):
    ui = ScriptedUI()
    s, ctx = make(tmp_path, ui, quick=True)
    r = TaskCompleteTool().run({"summary": "Done: built it"}, ctx)
    assert s.phase is Phase.IDLE and r.output == "Done: built it" and not r.is_error


def test_interaction_tools_registered_and_not_mutating():
    reg = default_registry(ctx_online=False)
    for name in ("ask_user", "plan", "task_complete"):
        tool = reg.get(name)
        assert tool is not None and tool.mutating is False
    assert reg.get("plan").parameters["required"] == ["title", "steps"]


def test_scripted_ui_defaults_and_records():
    ui = ScriptedUI(answers=["a"])
    assert ui.ask("q", None) == "a" and ui.ask("q2", ["x"]) == ""
    assert ui.confirm("run it?") == "yes" and ui.confirm("again?", allow_always=True) == "yes"
    ui.text("t")
    ui.notice("n")
    ui.tool_started("read_file", {"path": "a"})
    ui.tool_finished("read_file", ToolResult("ok"))
    assert ui.texts == ["t"] and ui.notices == ["n"]
    assert ui.confirms == [("run it?", False), ("again?", True)]
    assert ScriptedUI(confirm="no").confirm("x") == "no"


def test_a_repeated_question_gets_the_earlier_answer_without_asking_again(tmp_path):
    ui = ScriptedUI(answers=["SQLite", "unused"])
    s, ctx = make(tmp_path, ui)
    tool = AskUserTool()
    tool.run({"question": "Which database?"}, ctx)
    r = tool.run({"question": "Which database?"}, ctx)
    assert not r.is_error and "already" in r.output and "SQLite" in r.output and "plan" in r.output
    assert len(ui.questions) == 1 and s.pending_decisions == ["Which database? -> SQLite"]


def test_questions_stop_at_the_limit_and_point_to_the_plan(tmp_path):
    from petru.tools.interaction import MAX_DESIGN_QUESTIONS

    ui = ScriptedUI(answers=[f"a{i}" for i in range(MAX_DESIGN_QUESTIONS + 1)])
    s, ctx = make(tmp_path, ui)
    tool = AskUserTool()
    for i in range(MAX_DESIGN_QUESTIONS):
        tool.run({"question": f"q{i}?"}, ctx)
    r = tool.run({"question": "one more?"}, ctx)
    assert not r.is_error and "plan" in r.output and len(ui.questions) == MAX_DESIGN_QUESTIONS
