"""The UI contract the agent loop talks to, plus a scripted implementation for tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, Protocol

from petru.agent.state import Plan
from petru.tools.base import ToolResult

ConfirmAnswer = Literal["yes", "no", "always"]
PlanAction = Literal["confirm", "edit", "reject"]


class UIPort(Protocol):
    def ask(self, question: str, options: list[str] | None) -> str: ...

    def confirm(self, prompt: str, allow_always: bool = False) -> ConfirmAnswer: ...

    def show_plan(self, plan: Plan) -> PlanAction: ...

    def edit_plan(self, plan: Plan) -> Plan: ...

    def text(self, delta: str) -> None: ...

    def tool_started(self, name: str, args: dict) -> None: ...

    def tool_finished(self, name: str, result: ToolResult) -> None: ...

    def notice(self, message: str) -> None: ...


class ScriptedUI:
    """Answers from a script and records everything; used by tests and end-to-end demos."""

    def __init__(
        self,
        answers: list[str] | None = None,
        confirm: ConfirmAnswer = "yes",
        plan_action: PlanAction = "confirm",
        edited_steps: list[str] | None = None,
    ) -> None:
        self._answers = list(answers or [])
        self._confirm = confirm
        self._plan_action = plan_action
        self._edited_steps = edited_steps
        self.questions: list[tuple[str, list[str] | None]] = []
        self.confirms: list[tuple[str, bool]] = []
        self.plans: list[Plan] = []
        self.texts: list[str] = []
        self.notices: list[str] = []
        self.tool_events: list[tuple] = []

    def ask(self, question: str, options: list[str] | None) -> str:
        self.questions.append((question, options))
        return self._answers.pop(0) if self._answers else ""

    def confirm(self, prompt: str, allow_always: bool = False) -> ConfirmAnswer:
        self.confirms.append((prompt, allow_always))
        return self._confirm

    def show_plan(self, plan: Plan) -> PlanAction:
        self.plans.append(plan)
        return self._plan_action

    def edit_plan(self, plan: Plan) -> Plan:
        if self._edited_steps is None:
            return plan
        return replace(plan, steps=list(self._edited_steps))

    def text(self, delta: str) -> None:
        self.texts.append(delta)

    def tool_started(self, name: str, args: dict) -> None:
        self.tool_events.append(("start", name, args))

    def tool_finished(self, name: str, result: ToolResult) -> None:
        self.tool_events.append(("end", name, result.is_error))

    def notice(self, message: str) -> None:
        self.notices.append(message)
