"""The full-screen view's conversation and its UIPort, driven from two threads as the app drives them."""

import re
import subprocess
import threading
import time

from petru.agent.cancel import Cancelled, CancelToken
from petru.tools.base import ToolResult
from petru.tui.screen_ui import Pending, ScreenUI
from petru.tui.transcript import Transcript

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run_in_thread(fn, *args):
    out: dict = {}

    def target():
        try:
            out["value"] = fn(*args)
        except BaseException as exc:  # noqa: BLE001 - the test inspects what came out
            out["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, out


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert condition()


def make_ui(project=None):
    return ScreenUI(Transcript(), CancelToken(), project=project)


def shown(transcript, width=80, height=10):
    return [ANSI.sub("", line).rstrip() for line in transcript.visible(width, height).splitlines()]


def test_ask_blocks_until_answered_and_a_digit_picks_an_option():
    ui = make_ui()
    thread, out = run_in_thread(ui.ask, "Which runner?", ["pytest", "unittest"])
    wait_for(lambda: ui.pending is not None)
    assert ui.pending == Pending("ask", "Which runner?", ["pytest", "unittest"]) and thread.is_alive()
    ui.answer("2")
    thread.join(2)
    assert out["value"] == "unittest" and ui.pending is None


def test_esc_while_a_question_waits_raises_cancelled():
    ui = make_ui()
    thread, out = run_in_thread(ui.confirm, "Run it?", True)
    wait_for(lambda: ui.pending is not None)
    ui.cancel.cancel()
    thread.join(2)
    assert isinstance(out["error"], Cancelled) and ui.pending is None


def test_text_typed_while_a_question_waits_answers_it_not_the_queue():
    ui = make_ui()
    thread, out = run_in_thread(ui.confirm, "Run it?", True)
    wait_for(lambda: ui.pending is not None)
    assert ui.pending.choices == ["yes", "no", "always"]
    ui.answer("y")
    thread.join(2)
    assert out["value"] == "yes" and ui.take_messages() == []


def test_a_plan_is_confirmed_by_click_or_by_enter():
    from petru.agent.state import Plan

    ui = make_ui()
    for typed, expected in (("reject", "reject"), ("", "confirm")):
        thread, out = run_in_thread(ui.show_plan, Plan("Todo", ["a"]))
        wait_for(lambda: ui.pending is not None)
        assert ui.pending.choices == ["confirm", "edit", "reject"]
        ui.answer(typed)
        thread.join(2)
        assert out["value"] == expected


def test_messages_typed_mid_turn_are_handed_over_once():
    ui = make_ui()
    ui.interject("why?")
    ui.interject("and the tests?")
    assert ui.take_messages() == ["why?", "and the tests?"] and ui.take_messages() == []


def test_text_and_reasoning_stream_into_separate_entries():
    ui = make_ui()
    for delta in "ab":
        ui.reasoning(delta)
    for delta in "cd":
        ui.text(delta)
    assert [(e.kind, e.body) for e in ui.transcript.entries] == [("reasoning", "ab"), ("text", "cd")]


def test_tool_lines_and_changed_files_follow_each_tool(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ui = make_ui(project=tmp_path)
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    ui.tool_started("write_file", {"path": "a.py"})
    ui.tool_finished("write_file", ToolResult("wrote a.py", False))
    assert [e.body for e in ui.transcript.entries] == ["▸ write_file path=a.py", "  ✓ wrote a.py"]
    assert ui.files == ["+ a.py"]


def test_transcript_follows_the_end_until_scrolled_up():
    transcript = Transcript()
    for i in range(100):
        transcript.add("notice", f"line {i}")
    assert shown(transcript)[-1] == "line 99" and len(shown(transcript)) == 10
    transcript.page_up(10)
    assert shown(transcript)[-1] == "line 89" and not transcript.following
    transcript.page_down(10)
    assert shown(transcript)[-1] == "line 99" and transcript.following


def test_render_survives_a_narrow_terminal():
    transcript = Transcript()
    transcript.add("text", "# Title\n\nsome **bold** text and `code`")
    transcript.add("tool", "▸ run_checks")
    for width in (1, 20):
        assert transcript.visible(width, 5)
