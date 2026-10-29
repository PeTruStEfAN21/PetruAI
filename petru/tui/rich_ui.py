"""Terminal rendering and prompts. No agent logic lives here: it only shows and asks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from petru.agent.state import Plan
from petru.tools.base import ToolResult
from petru.tui.port import ConfirmAnswer, PlanAction

MAX_ARG_CHARS = 60
MAX_RESULT_CHARS = 100
NO_USER_ANSWER = "No user available; decide yourself and proceed."


def _default_prompt(message: str) -> str:
    from prompt_toolkit.shortcuts import prompt

    return prompt(message)


def _short(value: object, limit: int = MAX_ARG_CHARS) -> str:
    text = str(value).replace("\n", "\\n")
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def summarize_args(args: dict) -> str:
    parts = []
    for key, value in args.items():
        if isinstance(value, str) and len(value) > MAX_ARG_CHARS:
            parts.append(f"{key}=<{len(value)} chars>")
        else:
            parts.append(f"{key}={_short(value)}")
    return " ".join(parts)


def pick_option(answer: str, options: list[str] | None) -> str | None:
    """The option a reply names, by its number or its exact text; None for anything else."""
    options = options or []
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return options[int(answer) - 1]
    return answer if answer in options else None


def parse_confirm(answer: str, allow_always: bool) -> ConfirmAnswer:
    answer = answer.strip().lower()
    if answer in ("y", "yes"):
        return "yes"
    if allow_always and answer in ("a", "always"):
        return "always"
    return "no"


def parse_plan_action(answer: str) -> PlanAction:
    """Enter (or anything unknown) confirms, as the prompt says."""
    answer = answer.strip().lower()
    if answer in ("e", "edit"):
        return "edit"
    if answer in ("r", "reject"):
        return "reject"
    return "confirm"


def summarize_result(result: ToolResult) -> str:
    lines = [line for line in result.output.splitlines() if line.strip()]
    if not lines:
        return "(no output)"
    head = _short(lines[0], MAX_RESULT_CHARS)
    return head if len(lines) == 1 else f"{head} (+{len(lines) - 1} lines)"


class RichUI:
    """Interactive UI: streaming Markdown answers, compact tool lines, prompt_toolkit questions."""

    def __init__(self, console: Console, prompt_fn: Callable[[str], str] = _default_prompt) -> None:
        self.console = console
        self._prompt = prompt_fn
        self._buffer = ""
        self._live: Live | None = None

    # -- streaming text ---------------------------------------------------

    def text(self, delta: str) -> None:
        self._buffer += delta
        if self._live is None:
            self._live = Live(
                Markdown(self._buffer),
                console=self.console,
                refresh_per_second=8,
                vertical_overflow="visible",
            )
            self._live.start()
        else:
            self._live.update(Markdown(self._buffer))

    def flush(self) -> None:
        """End the streamed answer; called after every turn and before any prompt or tool line."""
        if self._live is not None:
            self._live.update(Markdown(self._buffer))
            self._live.stop()
            self._live = None
        elif self._buffer:
            self.console.print(Markdown(self._buffer))
        self._buffer = ""

    # -- tool lines -------------------------------------------------------

    def tool_started(self, name: str, args: dict) -> None:
        self.flush()
        self.console.print(f"[cyan]▸ {name}[/] {summarize_args(args)}", markup=True, highlight=False)

    def tool_finished(self, name: str, result: ToolResult) -> None:
        mark = "[red]✗[/]" if result.is_error else "[green]✓[/]"
        self.console.print(f"  {mark} {summarize_result(result)}", markup=True, highlight=False)

    def notice(self, message: str) -> None:
        self.flush()
        self.console.print(f"[yellow]{message}[/]", markup=True, highlight=False)

    def reasoning(self, delta: str) -> None:
        self.console.print(delta, style="dim", end="", markup=False, highlight=False)

    def take_messages(self) -> list[str]:
        return []  # the line prompt is not open while a turn runs

    # -- questions --------------------------------------------------------

    def _read(self, message: str = "> ") -> str:
        return self._prompt(message).strip()

    def ask(self, question: str, options: list[str] | None) -> str:
        self.flush()
        self.console.print(f"[bold]? {question}[/]", markup=True, highlight=False)
        for i, option in enumerate(options or [], start=1):
            self.console.print(f"  {i}. {option}", markup=False, highlight=False)
        while True:
            answer = self._read()
            picked = pick_option(answer, options)
            if picked or answer:
                return picked or answer

    def confirm(self, prompt: str, allow_always: bool = False) -> ConfirmAnswer:
        self.flush()
        choices = "[y]es / [n]o" + (" / [a]lways" if allow_always else "")
        self.console.print(f"[bold]{prompt}[/] {choices}", markup=True, highlight=False)
        return parse_confirm(self._read(), allow_always)

    def show_plan(self, plan: Plan) -> PlanAction:
        self.flush()
        self.console.print(f"[bold]Plan: {plan.title}[/]", markup=True, highlight=False)
        for i, step in enumerate(plan.steps, start=1):
            self.console.print(f"  {i}. {step}", markup=False, highlight=False)
        if plan.decisions:
            self.console.print("Decisions:", markup=False)
            for decision in plan.decisions:
                self.console.print(f"  - {decision}", markup=False, highlight=False)
        self.console.print("[c]onfirm / [e]dit / [r]eject (Enter = confirm)", markup=False)
        return parse_plan_action(self._read())

    def edit_plan(self, plan: Plan) -> Plan:
        self.console.print(
            "Type the new steps, one per line; an empty line ends (empty input keeps the plan)."
        )
        steps: list[str] = []
        while True:
            line = self._read(f"{len(steps) + 1}. ")
            if not line:
                break
            steps.append(line)
        return replace(plan, steps=steps) if steps else plan


class NonInteractiveUI:
    """For `petru -p`: no user to ask; tool lines go to the console, the answer is returned by the loop."""

    def __init__(self, console: Console, yolo: bool = False) -> None:
        self.console = console
        self.yolo = yolo

    def ask(self, question: str, options: list[str] | None) -> str:
        return NO_USER_ANSWER

    def confirm(self, prompt: str, allow_always: bool = False) -> ConfirmAnswer:
        return "yes" if self.yolo else "no"

    def show_plan(self, plan: Plan) -> PlanAction:
        return "confirm"

    def edit_plan(self, plan: Plan) -> Plan:
        return plan

    def text(self, delta: str) -> None:
        pass

    def tool_started(self, name: str, args: dict) -> None:
        self.console.print(f"▸ {name} {summarize_args(args)}", markup=False, highlight=False)

    def tool_finished(self, name: str, result: ToolResult) -> None:
        self.console.print(f"  {'✗' if result.is_error else '✓'} {summarize_result(result)}", markup=False)

    def notice(self, message: str) -> None:
        self.console.print(message, markup=False, highlight=False)

    def reasoning(self, delta: str) -> None:
        pass

    def take_messages(self) -> list[str]:
        return []

    def flush(self) -> None:
        pass
