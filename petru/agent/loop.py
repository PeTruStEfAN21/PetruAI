"""The agent loop: one user turn = model requests and tool executions until the model answers in text."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from petru.agent.cancel import Cancelled, CancelToken
from petru.agent.context import build_system_prompt, compact_if_needed
from petru.agent.permissions import DESIGN_ALLOWED, decide
from petru.agent.state import Phase, Session
from petru.agent.toolcalls import (
    canonical_call,
    extract_tool_calls,
    repair_json,
    sanitize_arguments,
    strip_text_tool_calls,
    validate_arguments,
)
from petru.providers.base import ChatProvider, ToolCall
from petru.tools.base import ToolContext, ToolResult
from petru.tools.git import tree_fingerprint
from petru.tools.registry import ToolRegistry
from petru.tools.shell import truncate_output
from petru.tui.port import UIPort

CANCELLED = "Cancelled by the user."


def _is_context_overflow(exc: Exception) -> bool:
    text = str(exc).lower()
    return "exceeds" in text and ("context" in text or "tokens" in text)


QUESTION_STRIKES = 2  # refused questions after which DESIGN stops offering ask_user
MAX_TOOL_RESULT_CHARS = 24_000  # a backstop above read_file's 400 lines; tools keep their own, smaller limits
REPEAT_LIMIT = 5  # calls repeated with the same result and no file changed, after which the turn stops
REPEAT_NOTE = (
    "\n\nNote: you made this same call before and nothing changed since, so its result is the same. Do not "
    "run it again: change the code it points at, delegate the missing piece, or say what blocks you."
)
DURATION = re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s)\b|\(\d+:\d\d:\d\d\)")  # "in 0.39s", "(0:01:16)"


@dataclass
class Usage:
    """What the model did in this session, as /details shows it."""

    requests: int = 0
    prompt_tokens: int = 0  # of the last request: how full the context is now
    completion_tokens: int = 0  # every reply together
    model_seconds: float = 0.0  # waiting for replies, prompt processing included
    tool_calls: int = 0

    def record(self, prompt_tokens: int | None, completion_tokens: int | None, seconds: float, calls: int):
        self.requests += 1
        self.prompt_tokens = prompt_tokens if prompt_tokens is not None else self.prompt_tokens
        self.completion_tokens += completion_tokens or 0
        self.model_seconds += seconds
        self.tool_calls += calls


def _same_result_key(output: str) -> int:
    """Two runs of the same checks differ in their timings: masked, the same result compares equal."""
    return hash(DURATION.sub("#", output))


def _recordable(call: ToolCall) -> str:
    """Arguments as they go into the transcript. llama-server re-parses them to render the chat template and
    answers 500 to every later request if they are not JSON, so unparseable ones are recorded as {} (the tool
    result already tells the model its call was invalid)."""
    if call.arguments is not None:
        return call.raw_arguments
    return "{}"


def output_budget(ctx_tokens: int) -> int:
    """Tokens one reply may take: a quarter of the context, so a whole source file fits in one write_file
    call (4096 cut large files off mid-call), and the transcript is compacted early enough to leave it."""
    return max(4096, min(16384, ctx_tokens // 4))


def _json_problem(raw: str) -> str:
    """Where the arguments stopped being JSON: the model never sees its broken call again (it is recorded as
    {}), so without this it repeats the same mistake."""
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        near = raw[max(0, exc.pos - 20) : exc.pos + 20]
        return f"{exc.msg} at line {exc.lineno} column {exc.colno}, near {near!r}"
    return "it is not an object"


class Agent:
    def __init__(
        self,
        provider: ChatProvider,
        registry: ToolRegistry,
        ui: UIPort,
        session: Session,
        repo_root: Path,
        ctx_tokens: int,
        online: bool,
        max_iterations: int = 40,
        max_invalid_retries: int = 3,
        deadline: float | None = None,
        cancel: CancelToken | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.ui = ui
        self.session = session
        self.repo_root = repo_root
        self.ctx_tokens = ctx_tokens
        self.output_tokens = output_budget(ctx_tokens)
        self.online = online
        self.max_iterations = max_iterations
        self.max_invalid_retries = max_invalid_retries
        self.deadline = deadline  # time.monotonic() past which a turn stops itself (a scripted run's limit)
        self.stop_reason: str | None = None
        self._changes = 0  # file changes so far: a repeated call is only useless while this stays put
        self._seen: dict[tuple[str, str], tuple[int, int]] = {}  # call -> (changes, result) when last made
        self.repeats = 0  # useless repeats since the last file change
        self.usage = Usage()
        self.cancel = cancel or CancelToken()  # Esc in the full-screen UI

    # -- transcript helpers -------------------------------------------------

    def _refresh_system_prompt(self) -> None:
        prompt = build_system_prompt(self.session, self.repo_root, self.online)
        messages = self.session.messages
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = prompt
        else:
            messages.insert(0, {"role": "system", "content": prompt})

    def _allowed_tool_names(self) -> list[str]:
        phase = self.session.phase
        if phase is Phase.BUILD:
            return self.registry.names()
        if phase is Phase.DESIGN:
            names = [name for name in self.registry.names() if name in DESIGN_ALLOWED]
            if self.session.turned_away_questions >= QUESTION_STRIKES:  # a looping model: leave it the plan
                names = [name for name in names if name != "ask_user"]
            return names
        return []  # IDLE: the task is complete, the model only answers in text

    @staticmethod
    def _assistant_message(content: str, calls: list[ToolCall]) -> dict:
        return {
            "role": "assistant",
            "content": strip_text_tool_calls(content or ""),
            "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": _recordable(c)}}
                for c in calls
            ],
        }

    @staticmethod
    def _tool_message(call: ToolCall, content: str) -> dict:
        return {"role": "tool", "tool_call_id": call.id, "content": content}

    # -- one tool call ------------------------------------------------------

    def _invalid(self, reason: str, allowed: list[str]) -> str:
        return f"Invalid tool call: {reason}. Available tools: {', '.join(allowed) or '(none)'}"

    def _execute(self, call: ToolCall, allowed: list[str]) -> tuple[str, bool]:
        """Run one call; returns (tool message content, was_invalid)."""
        tool = self.registry.get(call.name)
        if tool is None:
            return self._invalid(f"unknown tool {call.name!r}", allowed), True
        args = call.arguments
        if args is None:
            args = repair_json(call.raw_arguments)
        if args is None:
            problem = _json_problem(call.raw_arguments)
            reason = (
                f"arguments of {call.name} are not a JSON object ({problem}). Escape quotes, backslashes and "
                "newlines inside strings; put long code in a file with write_file and run that file instead"
            )
            return self._invalid(reason, allowed), True
        args = sanitize_arguments(args)
        errors = validate_arguments(tool.parameters, args)
        if errors:
            return self._invalid(f"{call.name} arguments: " + "; ".join(errors), allowed), True

        if self.session.phase is Phase.IDLE:
            return "Denied: the task is complete; answer the user in plain text.", False
        decision = decide(tool, args, self.session)
        if decision.kind == "deny":
            return f"Denied: {decision.reason}", False
        if decision.kind == "ask":
            answer = self.ui.confirm(f"Run {call.name} {args}?", allow_always=True)
            if answer == "no":
                return "User declined.", False
            if answer == "always":
                self.session.always_allow.add(call.name)

        ctx = ToolContext(self.session.project_root, self.online, self.ui, self.session)
        before = tree_fingerprint(self.session.project_root) if tool.may_change_files else None
        self.ui.tool_started(call.name, args)
        try:
            result = tool.run(args, ctx)
        except Exception as exc:  # a buggy tool must not end the session
            result = ToolResult(f"{type(exc).__name__}: {exc}", True)
        self.ui.tool_finished(call.name, result)
        if call.name == "run_checks":
            self.session.unverified_changes = result.is_error
        elif (tool.changes_files and not result.is_error) or (
            tool.may_change_files
            and (before is None or tree_fingerprint(self.session.project_root) != before)
        ):
            self.session.unverified_changes = True
            self._changes, self.repeats = self._changes + 1, 0
        output = truncate_output(result.output, MAX_TOOL_RESULT_CHARS)  # one result must not fill the context
        if self._repeated(call.name, args, result.output):
            output += REPEAT_NOTE
        return (f"ERROR: {output}" if result.is_error else output), False

    def _repeated(self, name: str, args: dict, output: str) -> bool:
        """The same call, the same result and no file changed since: running it again tells nothing new."""
        key, state = (name, json.dumps(args, sort_keys=True)), (self._changes, _same_result_key(output))
        repeated = self._seen.get(key) == state
        self._seen[key] = state
        self.repeats += repeated
        return repeated

    # -- the turn -----------------------------------------------------------

    def run_turn(self, text: str, quick: bool = False) -> str:
        """Run one user prompt to completion and return the model's final text."""
        session = self.session
        session.start_turn(text, quick=quick)
        self.cancel.reset()  # an Esc from before this prompt must not stop it
        self.stop_reason = None
        self.repeats = 0  # a new prompt gives the model a fresh chance
        invalid_count = 0
        provider_errors = 0
        last_text = ""
        while True:
            if self.deadline is not None and time.monotonic() >= self.deadline:
                return self._stop("time limit", "Time limit reached.", last_text)
            if session.turn_tool_iterations >= self.max_iterations:
                return self._stop(
                    "iteration limit", f"Iteration limit ({self.max_iterations}) reached.", last_text
                )
            self._refresh_system_prompt()
            compact_if_needed(session, self.provider, self.ctx_tokens, self.output_tokens)
            allowed = self._allowed_tool_names()
            asked = time.monotonic()
            try:
                self.cancel.check()
                result = self.provider.complete(
                    session.messages,
                    self.registry.schemas(allowed),
                    on_text=self.ui.text,
                    temperature=round(0.2 + 0.3 * provider_errors, 2),  # a retry samples differently
                    max_tokens=self.output_tokens,
                    on_reasoning=self.ui.reasoning,
                    cancel=self.cancel,
                )
            except Cancelled:
                return self._stop("cancelled", "Turn cancelled.", last_text)
            except Exception as exc:  # server 500 (unparseable tool call), timeout, connection reset
                provider_errors += 1
                if provider_errors >= self.max_invalid_retries:
                    message = f"Model request failed {provider_errors} times: {exc}"
                    return self._stop("provider error", message, last_text)
                self.ui.notice(
                    f"Model error: {exc}. Retrying ({provider_errors}/{self.max_invalid_retries - 1})..."
                )
                if _is_context_overflow(exc):
                    compact_if_needed(session, self.provider, self.ctx_tokens, self.output_tokens, force=True)
                continue
            calls = [canonical_call(c) for c in extract_tool_calls(result)]
            self.usage.record(
                result.prompt_tokens, result.completion_tokens, time.monotonic() - asked, len(calls)
            )
            last_text = strip_text_tool_calls(result.content or "")
            if not calls:
                session.messages.append({"role": "assistant", "content": result.content or ""})
                return last_text

            session.turn_tool_iterations += 1
            assistant = self._assistant_message(result.content, calls)
            outputs: list[dict] = []
            try:
                for call in calls:
                    content, was_invalid = self._execute(call, allowed)
                    if was_invalid and result.finish_reason == "length":
                        content = self._invalid(
                            f"your reply was cut off at the {self.output_tokens}-token output limit before "
                            "this call was complete. Write a large file in parts: write_file with the first "
                            "part, then write_file with append=true for each next part",
                            allowed,
                        )
                    invalid_count += was_invalid
                    outputs.append(self._tool_message(call, content))
                    self.cancel.check()
            except KeyboardInterrupt:
                outputs.extend(self._tool_message(call, CANCELLED) for call in calls[len(outputs) :])
                session.messages.extend([assistant, *outputs])
                return self._stop("cancelled", "Turn cancelled.", last_text)
            session.messages.extend([assistant, *outputs])
            for typed in self.ui.take_messages():  # typed while the tools ran: the model reads it next
                session.messages.append({"role": "user", "content": typed})
            if invalid_count >= self.max_invalid_retries:
                return self._stop(
                    "invalid tool calls", f"Giving up after {invalid_count} invalid tool calls.", last_text
                )
            if self.repeats >= REPEAT_LIMIT:
                message = f"Stopped: {self.repeats} calls gave the same result, no file changed in between."
                return self._stop("no progress", message, last_text)

    def _stop(self, reason: str, message: str, text: str) -> str:
        self.stop_reason = reason
        self.ui.notice(message)
        return text
