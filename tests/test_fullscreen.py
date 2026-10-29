"""The full-screen view end to end: keys go in through a pipe input, the agent runs in its own thread."""

import threading
import time

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput

from petru import cli
from petru.agent.cancel import Cancelled, CancelToken
from petru.agent.state import Phase
from petru.app import App
from petru.config import Config, default_tiers
from petru.tui.fullscreen import FullScreen
from petru.tui.screen_ui import ScreenUI
from petru.tui.transcript import Transcript
from tests.fakes import FakeProvider, call, make_agent, result
from tests.test_cli import FakeManager

ENTER, ESC, CTRL_D = "\r", "\x1b", "\x04"


class Hanging(FakeProvider):
    """A reply that never comes, until Esc."""

    def complete(
        self, messages, tools, on_text=None, temperature=0.2, max_tokens=4096, cancel=None, **kwargs
    ):
        self.calls.append({"messages": messages})
        while not cancel.cancelled:
            time.sleep(0.01)
        raise Cancelled


class Crashing(FakeProvider):
    def complete(self, *args, **kwargs):
        raise RuntimeError("boom")


def make_screen(tmp_path, provider):
    cfg = Config(tmp_path, tmp_path / "models", tmp_path / "server.exe", tiers=default_tiers())
    transcript = Transcript()
    ui = ScreenUI(transcript, CancelToken(), project=tmp_path)
    agent = make_agent(provider, ui, tmp_path, cancel=ui.cancel)
    app = App(agent, FakeManager(cfg), cfg, cli.TeamModes(cfg, tmp_path, False), False, say=ui.info)
    return FullScreen(app, ui, transcript)


def text_of(screen):
    return "\n".join(entry.body for entry in screen.transcript.entries)


def wait_until(condition, timeout=10.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.02)
    return condition()


def drive(tmp_path, provider, steps):
    """Run the screen; `steps` are (condition, keys): each waits until condition(screen) holds, then types its
    keys. Returns the screen, the seconds it took to exit after the last keys, and which conditions held."""
    held: list[bool] = []
    timing: dict = {}
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        screen = make_screen(tmp_path, provider)

        def driver():
            for condition, keys in steps:
                held.append(wait_until(lambda condition=condition: condition(screen)))
                pipe.send_text(keys)
            timing["sent"] = time.monotonic()
            if not wait_until(lambda: not screen.application.is_running, 8):
                screen.application.loop.call_soon_threadsafe(screen.application.exit)  # never hang the suite

        threading.Thread(target=driver, daemon=True).start()
        screen.run()
    return screen, time.monotonic() - timing.get("sent", time.monotonic()), held


def running(screen):
    return screen.application.is_running


def test_a_request_runs_in_the_background_and_its_tool_lines_show(tmp_path):
    write = call("write_file", {"path": "hello.py", "content": "print('hi')"})
    provider = FakeProvider([result(tool_calls=[write]), result(content="Wrote hello.py.")])
    steps = [
        (running, "/quick write hello" + ENTER),
        (lambda s: len(provider.calls) == 2 and not s.app.busy, CTRL_D),
    ]
    screen, _, held = drive(tmp_path, provider, steps)
    assert all(held) and (tmp_path / "hello.py").is_file()
    assert "▸ write_file" in text_of(screen) and "Wrote hello.py." in text_of(screen)


def test_esc_stops_a_reply_in_flight(tmp_path):
    provider = Hanging([])
    steps = [
        (running, "/quick never answers" + ENTER),
        (lambda s: bool(provider.calls), ESC),
        (lambda s: not s.app.busy, CTRL_D),
    ]
    screen, _, held = drive(tmp_path, provider, steps)
    assert all(held) and screen.app.agent.stop_reason == "cancelled" and "Turn cancelled." in text_of(screen)


def test_typing_a_number_answers_the_question(tmp_path):
    ask = call("ask_user", {"question": "Runner?", "options": ["pytest", "unittest"]})
    provider = FakeProvider([result(tool_calls=[ask]), result(content="Noted.")])
    steps = [
        (running, "make a cli" + ENTER),
        (lambda s: s.ui.pending is not None, "1" + ENTER),
        (lambda s: len(provider.calls) == 2 and not s.app.busy, CTRL_D),
    ]
    _, _, held = drive(tmp_path, provider, steps)
    assert all(held) and "pytest" in provider.calls[1]["messages"][-1]["content"]


def test_a_crash_in_the_agent_thread_is_shown_and_the_app_stays_usable(tmp_path):
    steps = [
        (running, "/quick go" + ENTER),
        (lambda s: "boom" in text_of(s) and not s.app.busy, "/status" + ENTER),
        (lambda s: "phase=" in text_of(s), CTRL_D),
    ]
    screen, _, held = drive(tmp_path, Crashing([]), steps)
    assert all(held) and "boom" in text_of(screen)


def test_ctrl_d_while_busy_cancels_and_exits(tmp_path):
    provider = Hanging([])
    steps = [(running, "/quick never answers" + ENTER), (lambda s: bool(provider.calls), CTRL_D)]
    screen, took, held = drive(tmp_path, provider, steps)
    assert all(held) and took < 6 and screen.app.agent.cancel.cancelled


def click(fragments, label):
    handler = next(fragment[2] for fragment in fragments if label in fragment[1])
    event = MouseEvent(None, MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset())
    return handler(event)


def test_clicking_yolo_toggles_it_and_a_greyed_team_does_nothing(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        screen = make_screen(tmp_path, FakeProvider([]))
        click(screen.toolbar_fragments(), "Yolo")
        assert screen.app.session.yolo
        screen.app.session.phase = Phase.DESIGN
        registry = screen.app.agent.registry
        click(screen.toolbar_fragments(), "Team")
        assert screen.app.agent.registry is registry and screen.worker is None
        team = [fragment for fragment in screen.toolbar_fragments() if "Team" in fragment[1]]
        assert "disabled" in team[0][0]


def test_the_panel_hides_on_a_narrow_terminal(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        screen = make_screen(tmp_path, FakeProvider([]))
        assert not screen.panel_visible(100) and screen.panel_visible(120)
        screen.toggle_panel()
        assert not screen.panel_visible(120)


def test_cli_picks_the_full_screen_only_on_a_wide_terminal_without_plain(tmp_path, monkeypatch):
    from tests.test_cli import patch_runtime

    patch_runtime(monkeypatch, tmp_path, [])
    used: list[str] = []
    monkeypatch.setattr(cli, "wants_fullscreen", lambda: True)
    monkeypatch.setattr(cli, "run_fullscreen", lambda app, ui, transcript: used.append("screen"))
    monkeypatch.setattr(cli, "repl", lambda app, console: used.append("lines"))
    project = str(tmp_path / "p")
    assert cli.main(["--project", project, "--model", "fast"]) == 0
    assert cli.main(["--project", project, "--model", "fast", "--plain"]) == 0
    assert used == ["screen", "lines"]


def test_a_stale_model_menu_cannot_start_a_second_worker(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        screen = make_screen(tmp_path, Hanging([]))
        screen.state.menu = ["fast", "quality"]
        screen.submit("/quick never answers")
        assert screen.state.menu is None
        first = screen.worker
        screen._pick_model("quality")
        assert screen.worker is first and screen.app.manager.started == []
        screen.app.agent.cancel.cancel()
        first.join(5)


def test_esc_gives_back_what_was_typed_instead_of_running_it(tmp_path):
    provider = Hanging([])
    steps = [
        (running, "/quick never answers" + ENTER),
        (lambda s: bool(provider.calls), "also do y" + ENTER),
        (lambda s: "(at the next step)" in text_of(s), ESC),
        (lambda s: not s.app.busy and s.input.text == "also do y", "\x15" + CTRL_D),
    ]
    _, _, held = drive(tmp_path, provider, steps)
    assert all(held) and len(provider.calls) == 1


def test_enter_just_as_a_turn_ends_starts_the_next_turn(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        provider = FakeProvider([result(content="first"), result(content="second")])
        screen = make_screen(tmp_path, provider)
        take, late = screen.ui.take_messages, []

        def take_then_enter():
            typed = take()
            if not typed and not late:  # Enter lands between the last look at the queue and the thread's end
                late.append(threading.Thread(target=screen.submit, args=("late",), daemon=True))
                late[0].start()
                late[0].join(0.2)
            return typed

        screen.ui.take_messages = take_then_enter
        screen.submit("/quick first")
        assert wait_until(lambda: len(provider.calls) == 2 and not screen.app.busy, 5)
        assert provider.calls[1]["messages"][-1] == {"role": "user", "content": "late"}
