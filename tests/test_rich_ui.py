import io

from rich.console import Console

from petru.agent.state import Plan
from petru.tools.base import ToolResult
from petru.tui.rich_ui import NonInteractiveUI, RichUI


def make_ui(lines):
    out = io.StringIO()
    console = Console(file=out, force_terminal=False, width=80, color_system=None)
    answers = list(lines)
    ui = RichUI(console, prompt_fn=lambda _: answers.pop(0))
    return ui, out


def test_confirm_maps_single_letters():
    ui, _ = make_ui(["y", "n", "a", "", "A"])
    assert ui.confirm("Run shell?", allow_always=True) == "yes"
    assert ui.confirm("Run shell?", allow_always=True) == "no"
    assert ui.confirm("Run shell?", allow_always=True) == "always"
    assert ui.confirm("Run shell?", allow_always=True) == "no"  # empty answer is the safe default
    assert ui.confirm("Run shell?", allow_always=False) == "no"  # "always" not offered -> not accepted


def test_ask_number_selects_option_and_text_is_free_form():
    ui, out = make_ui(["2", "", "something else"])
    assert ui.ask("Database?", ["SQLite", "Postgres"]) == "Postgres"
    assert ui.ask("Database?", ["SQLite", "Postgres"]) == "something else"  # empty line is asked again
    text = out.getvalue()
    assert "Database?" in text and "1. SQLite" in text and "2. Postgres" in text


def test_show_plan_renders_steps_and_maps_actions():
    plan = Plan("Todo app", ["write todo.py", "write tests"], decisions=["Database? -> SQLite"])
    ui, out = make_ui(["c", "e", "r", ""])
    assert ui.show_plan(plan) == "confirm"
    assert ui.show_plan(plan) == "edit"
    assert ui.show_plan(plan) == "reject"
    assert ui.show_plan(plan) == "confirm"
    text = out.getvalue()
    assert "Todo app" in text and "1. write todo.py" in text and "2. write tests" in text and "SQLite" in text


def test_edit_plan_reads_steps_until_empty_line_and_keeps_plan_when_empty():
    plan = Plan("T", ["old"])
    ui, _ = make_ui(["new one", "new two", "", ""])
    edited = ui.edit_plan(plan)
    assert edited.steps == ["new one", "new two"] and edited.title == "T"
    assert ui.edit_plan(plan).steps == ["old"]


def test_tool_lines_are_compact():
    ui, out = make_ui([])
    ui.tool_started("write_file", {"path": "a.py", "content": "x" * 500})
    ui.tool_finished("write_file", ToolResult("Wrote a.py (1 line)"))
    ui.tool_started("shell", {"command": "npm test"})
    ui.tool_finished("shell", ToolResult("boom\nexit code: 1", True))
    text = out.getvalue()
    assert "write_file" in text and "path=a.py" in text and "x" * 500 not in text
    assert "Wrote a.py" in text and "boom" in text


def test_text_streams_and_flush_ends_the_block():
    ui, out = make_ui([])
    ui.text("Hello ")
    ui.text("**world**")
    ui.flush()
    assert "Hello" in out.getvalue() and "world" in out.getvalue()


def test_notice_is_printed():
    ui, out = make_ui([])
    ui.notice("Iteration limit reached.")
    assert "Iteration limit reached." in out.getvalue()


def test_non_interactive_ui_answers_and_declines():
    out = io.StringIO()
    ui = NonInteractiveUI(Console(file=out, force_terminal=False, width=80, color_system=None))
    assert ui.ask("x?", None) == "No user available; decide yourself and proceed."
    assert ui.confirm("run?", allow_always=True) == "no"
    assert NonInteractiveUI(Console(file=out), yolo=True).confirm("run?") == "yes"
    assert ui.show_plan(Plan("T", ["s"])) == "confirm"
    ui.text("streamed")
    ui.tool_started("read_file", {"path": "a"})
    assert "streamed" not in out.getvalue() and "read_file" in out.getvalue()
