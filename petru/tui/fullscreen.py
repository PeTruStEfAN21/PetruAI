"""petru on the whole screen: a clickable bar on top, the conversation on the left, a panel on the right and
the prompt at the bottom. The agent runs in a worker thread; this thread only draws and reads keys."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    BufferControl,
    ConditionalContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.styles import Style

from petru.app import App
from petru.tui.commands import parse_command
from petru.tui.panel import panel_sections
from petru.tui.screen_ui import ScreenUI
from petru.tui.toolbar import model_choices, toolbar_items
from petru.tui.transcript import Transcript

PANEL_MIN_COLUMNS = 110  # narrower terminals give the whole width to the conversation
PANEL_MIN_WIDTH = 30
WHEEL_LINES = 3
QUIT_WAIT_S = 5.0  # how long quitting waits for a cancelled turn to wind down
WHILE_WORKING = {"details", "status", "help", "think", "yolo", "plan", "memory", "journal"}  # safe mid-turn

STYLE = Style.from_dict(
    {
        "bar": "bg:#1c2128 #adbac7",
        "bar.item": "bg:#2d333b #e6edf3",
        "bar.disabled": "bg:#1c2128 #545d68",
        "choices": "bg:#22272e",
        "choices.label": "bg:#22272e #768390",
        "choices.item": "bg:#2d333b #f0c674 bold",
        "panel.title": "bold #6cb6ff",
        "panel": "#adbac7",
        "separator": "#444c56",
        "prompt": "bold #8ddb8c",
    }
)


@dataclass
class ScreenState:
    panel_on: bool = True
    menu: list[str] | None = None  # the Model menu, while open


def _on_click(action: Callable[[], None]):
    def handler(event: MouseEvent):
        if event.event_type != MouseEventType.MOUSE_UP:
            return NotImplemented
        action()
        return None

    return handler


class _Conversation(FormattedTextControl):
    """The conversation, scrolled by the mouse wheel."""

    def __init__(self, screen: FullScreen) -> None:
        super().__init__(screen.conversation_text, focusable=False)
        self.screen = screen

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self.screen.transcript.page_up(WHEEL_LINES)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self.screen.transcript.page_down(WHEEL_LINES)
            return None
        return super().mouse_handler(mouse_event)


class FullScreen:
    def __init__(
        self, app: App, ui: ScreenUI, transcript: Transcript, history: History | None = None
    ) -> None:
        self.app, self.ui, self.transcript = app, ui, transcript
        self.state = ScreenState()
        self.worker: threading.Thread | None = None
        self._live = False  # a worker runs and still takes typed messages; changed only under _lock
        self._lock = threading.Lock()
        self.input = Buffer(
            multiline=False, history=history or InMemoryHistory(), accept_handler=self._accept
        )
        prompt_line = VSplit(
            [
                Window(FormattedTextControl(self._prompt), dont_extend_width=True),
                Window(BufferControl(self.input)),
            ],
            height=1,
        )
        body = VSplit(
            [
                Window(_Conversation(self), wrap_lines=False),
                ConditionalContainer(
                    VSplit(
                        [
                            Window(width=1, char="│", style="class:separator"),
                            Window(
                                FormattedTextControl(self._panel),
                                width=lambda: Dimension.exact(self._panel_width()),
                                wrap_lines=False,
                            ),
                        ]
                    ),
                    filter=Condition(lambda: self.panel_visible()),
                ),
            ]
        )
        root = HSplit(
            [
                Window(FormattedTextControl(self.toolbar_fragments), height=1, style="class:bar"),
                body,
                ConditionalContainer(
                    Window(FormattedTextControl(self.choices_fragments), height=1, style="class:choices"),
                    filter=Condition(self._choices_shown),
                ),
                prompt_line,
            ]
        )
        self.application: Application = Application(
            layout=Layout(root, focused_element=self.input),
            key_bindings=self._keys(),
            style=STYLE,
            full_screen=True,
            mouse_support=True,
            refresh_interval=0.5,
            min_redraw_interval=0.05,
        )
        self.application.ttimeoutlen = 0.05  # a lone Esc is a key, not the start of a sequence
        ui.refresh = self.application.invalidate

    # -- layout pieces ----------------------------------------------------------

    def _columns(self) -> int:
        return self.application.output.get_size().columns

    def panel_visible(self, columns: int | None = None) -> bool:
        columns = self._columns() if columns is None else columns
        return self.state.panel_on and columns >= PANEL_MIN_COLUMNS

    def _panel_width(self) -> int:
        return max(PANEL_MIN_WIDTH, self._columns() // 3)

    def _conversation_size(self) -> tuple[int, int]:
        size = self.application.output.get_size()
        width = size.columns - (self._panel_width() + 1 if self.panel_visible(size.columns) else 0)
        return width, size.rows - 2 - (1 if self._choices_shown() else 0)

    def conversation_text(self):
        width, height = self._conversation_size()
        return ANSI(self.transcript.visible(width, height))

    def _panel(self):
        out: list[tuple[str, str]] = []
        for title, lines in panel_sections(self.app, self.ui.files):
            out.append(("class:panel.title", f" {title}\n"))
            out.extend(("class:panel", f" {line}\n") for line in lines)
            out.append(("", "\n"))
        return out

    def _prompt(self):
        pending = self.ui.pending
        if pending is None:
            return [("class:prompt", "petru> ")]
        return [("class:prompt", f"{pending.prompt} " if pending.kind == "edit" else "answer> ")]

    def toolbar_fragments(self):
        out: list[tuple] = []
        for item in toolbar_items(self.app):
            style = "class:bar.item" if item.enabled else "class:bar.disabled"
            action = (lambda key=item.key: self.act(key)) if item.enabled else (lambda: None)
            out += [(style, f" {item.label} ", _on_click(action)), ("class:bar", " ")]
        return out

    def _choices_shown(self) -> bool:
        pending = self.ui.pending
        return self.state.menu is not None or (pending is not None and bool(pending.choices))

    def choices_fragments(self):
        if self.state.menu is not None:
            out: list[tuple] = [("class:choices.label", " Model: ")]
            for tier in self.state.menu:
                out += [("class:choices.item", f" {tier} ", _on_click(lambda t=tier: self._pick_model(t)))]
                out.append(("class:choices", " "))
            return [*out, ("class:choices.label", " Esc closes")]
        pending = self.ui.pending
        if pending is None:
            return []
        out = [("class:choices.label", " ")]
        for i, choice in enumerate(pending.choices, start=1):
            label = f" {i}. {choice} " if pending.kind == "ask" else f" {choice} "
            out += [("class:choices.item", label, _on_click(lambda c=choice: self.ui.answer(c)))]
            out.append(("class:choices", " "))
        return out

    # -- actions ------------------------------------------------------------------

    def working(self) -> bool:
        with self._lock:
            return self._live

    def act(self, key: str) -> None:
        """A click on the top bar."""
        if key == "model":
            self.state.menu = None if self.state.menu is not None else model_choices(self.app.cfg)
        elif key == "team":
            self._start(self.app.toggle_team)
        elif key == "think":
            self.app.toggle_think()
        elif key == "yolo":
            self.app.toggle_yolo()
        elif key == "panel":
            self.toggle_panel()
        self.application.invalidate()

    def toggle_panel(self) -> None:
        self.state.panel_on = not self.state.panel_on

    def _pick_model(self, tier: str) -> None:
        self.state.menu = None
        self.transcript.add("user", f"/model {tier}")
        self._start(lambda: self.app.switch_model(tier))

    def _start(self, job: Callable[[], None]) -> None:
        """Run a turn or a slow command in the worker thread, one at a time; what was typed after the model's
        last step becomes the next prompt, unless Esc stopped the turn: then it goes back to the prompt."""
        with self._lock:
            if self._live:  # a stale click (an open menu) must not start a second worker
                self.ui.info("Wait for the agent to stop (Esc stops it now).")
                return
            self._live = self.app.busy = True

        def work() -> None:
            typed: list[str] = []
            try:
                job()
                while True:
                    with self._lock:  # Enter at this moment either joins the queue or starts the next turn
                        typed = self.ui.take_messages()
                        stopped = self.app.agent.cancel.cancelled
                        if not typed or stopped:
                            self._live = self.app.busy = False
                            break
                    self.app.run_turn("\n".join(typed))
                if typed:
                    self.ui.info("Stopped. What you typed meanwhile is back at the prompt.")
                    self._give_back(" ".join(typed))
            except Exception as exc:  # a crash is shown; the screen stays usable
                self.ui.info(f"{type(exc).__name__}: {exc}")
            finally:
                with self._lock:
                    self._live = self.app.busy = False
                self.application.invalidate()

        self.worker = threading.Thread(target=work, name="petru-agent", daemon=True)
        self.worker.start()

    def _give_back(self, text: str) -> None:
        def put() -> None:
            self.input.text = text
            self.input.cursor_position = len(text)

        loop = self.application.loop
        if loop is not None and self.application.is_running:
            loop.call_soon_threadsafe(put)
        else:
            put()

    def _accept(self, buffer: Buffer) -> bool:
        self.submit(buffer.text)
        return False  # clear the line

    def submit(self, text: str) -> None:
        """Enter: answer the pending question, else pass a message to the working agent, else run it."""
        if self.ui.pending is not None:
            self.ui.answer(text)
            return
        text = text.strip()
        if not text:
            return
        self.state.menu = None
        cmd = parse_command(text)
        if cmd is None:
            with self._lock:  # checked and queued together, so the worker cannot end in between
                if self._live:
                    self.ui.interject(text)
                    return
        if cmd is not None and cmd.name == "exit":
            self.quit()
        elif self.working():
            if cmd.name in WHILE_WORKING:
                self.app.handle(text)
            else:
                self.ui.info(f"/{cmd.name} waits until the agent stops (Esc stops it now).")
        else:
            self.transcript.add("user", text)
            self._start(lambda: self.app.handle(text))
        self.application.invalidate()

    def escape(self) -> None:
        if self.state.menu is not None:
            self.state.menu = None
        elif self.working():
            self.app.agent.cancel.cancel()  # its callbacks close the reply and stop the commands

    def quit(self) -> None:
        if self.working():
            self.app.agent.cancel.cancel()
        if self.worker is not None:
            self.worker.join(QUIT_WAIT_S)
        self.application.exit()

    def _keys(self) -> KeyBindings:
        keys = KeyBindings()

        @keys.add("escape", eager=True)
        @keys.add("c-c")
        def _stop(event) -> None:
            self.escape()

        @keys.add("f2")
        def _panel(event) -> None:
            self.toggle_panel()

        @keys.add("pageup")
        def _up(event) -> None:
            self.transcript.page_up(self._conversation_size()[1])

        @keys.add("pagedown")
        def _down(event) -> None:
            self.transcript.page_down(self._conversation_size()[1])

        @keys.add("c-d")
        def _quit(event) -> None:
            if not self.input.text:
                self.quit()

        return keys

    def run(self) -> None:
        self.application.run()


def run_fullscreen(app: App, ui: ScreenUI, transcript: Transcript) -> None:
    history = Path.home() / ".petru" / "history"
    history.parent.mkdir(parents=True, exist_ok=True)
    ui.info(f"Petru ready. {app.status()}. /help for commands; Esc stops a step, F2 hides the panel.")
    FullScreen(app, ui, transcript, FileHistory(str(history))).run()
