"""The UIPort of the full-screen view. The agent runs in its own thread: what it shows goes into the
transcript, and its questions block that thread until the user answers at the prompt, clicks a choice, or
presses Esc."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from petru.agent.cancel import Cancelled, CancelToken
from petru.agent.state import Plan
from petru.tools.base import ToolResult
from petru.tui.panel import changed_files
from petru.tui.port import ConfirmAnswer, PlanAction
from petru.tui.rich_ui import parse_confirm, parse_plan_action, pick_option, summarize_args, summarize_result
from petru.tui.transcript import Kind, Transcript

PLAN_CHOICES = ["confirm", "edit", "reject"]
_ESC = object()  # what a waiting question receives when the user presses Esc


@dataclass(frozen=True)
class Pending:
    """What the prompt line answers now, and the choices the user can click."""

    kind: Literal["ask", "confirm", "plan", "edit"]
    prompt: str
    choices: list[str]


class ScreenUI:
    def __init__(
        self,
        transcript: Transcript,
        cancel: CancelToken,
        refresh: Callable[[], None] = lambda: None,
        project: Path | None = None,
    ) -> None:
        self.transcript, self.cancel, self.project = transcript, cancel, project
        self.refresh = refresh  # thread-safe redraw (Application.invalidate)
        self.pending: Pending | None = None
        self.files: list[str] = []  # the panel's Files section, refreshed after each tool
        self._answers: queue.Queue = queue.Queue()
        self._typed: list[str] = []
        self._lock = threading.Lock()

    def _show(self, kind: Kind, body: str) -> None:
        self.transcript.add(kind, body)
        self.refresh()

    # -- from the UI thread ---------------------------------------------------

    def answer(self, text: str) -> None:
        """The user's reply to the pending question, typed or clicked."""
        self._show("user", text or "(Enter)")
        self._answers.put(text)

    def interject(self, text: str) -> None:
        """Typed while the agent works: it reads it at its next step."""
        with self._lock:
            self._typed.append(text)
        self._show("user", f"{text} (at the next step)")

    # -- from the agent thread ------------------------------------------------

    def _wait(self, pending: Pending) -> str:
        while not self._answers.empty():  # an answer typed before this question is not its answer
            self._answers.get_nowait()
        self.pending = pending
        self.refresh()
        forget = self.cancel.on_cancel(lambda: self._answers.put(_ESC))
        try:
            answer = self._answers.get()
        finally:
            forget()
            self.pending = None
            self.refresh()
        if answer is _ESC:
            raise Cancelled
        return answer.strip()

    def ask(self, question: str, options: list[str] | None) -> str:
        numbered = "".join(f"\n  {i}. {option}" for i, option in enumerate(options or [], start=1))
        self._show("question", f"? {question}{numbered}")
        while True:
            answer = self._wait(Pending("ask", question, list(options or [])))
            picked = pick_option(answer, options)
            if picked or answer:
                return picked or answer

    def confirm(self, prompt: str, allow_always: bool = False) -> ConfirmAnswer:
        self._show("question", prompt)
        choices = ["yes", "no", *(["always"] if allow_always else [])]
        return parse_confirm(self._wait(Pending("confirm", prompt, choices)), allow_always)

    def show_plan(self, plan: Plan) -> PlanAction:
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(plan.steps, start=1))
        decisions = "".join(f"\n- {decision}" for decision in plan.decisions)
        self._show(
            "text", f"**Plan: {plan.title}**\n\n{steps}" + (f"\n\nDecisions:{decisions}" if decisions else "")
        )
        pending = Pending("plan", "confirm / edit / reject (Enter = confirm)", PLAN_CHOICES)
        return parse_plan_action(self._wait(pending))

    def edit_plan(self, plan: Plan) -> Plan:
        self._show(
            "notice", "Type the new steps, one per line; an empty line ends (empty input keeps the plan)."
        )
        steps: list[str] = []
        while answer := self._wait(Pending("edit", f"{len(steps) + 1}.", [])):
            steps.append(answer)
        return Plan(plan.title, steps, plan.decisions, plan.confirmed) if steps else plan

    def text(self, delta: str) -> None:
        self.transcript.stream("text", delta)
        self.refresh()

    def reasoning(self, delta: str) -> None:
        self.transcript.stream("reasoning", delta)
        self.refresh()

    def tool_started(self, name: str, args: dict) -> None:
        self._show("tool", f"▸ {name} {summarize_args(args)}".rstrip())

    def tool_finished(self, name: str, result: ToolResult) -> None:
        if self.project is not None:
            self.files = changed_files(self.project)
        self._show("tool", f"  {'✗' if result.is_error else '✓'} {summarize_result(result)}")

    def notice(self, message: str) -> None:
        self._show("notice", message)

    def take_messages(self) -> list[str]:
        with self._lock:
            typed, self._typed = self._typed, []
        return typed

    def flush(self) -> None:
        pass  # entries are complete as they arrive
