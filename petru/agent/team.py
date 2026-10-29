"""Team mode: the lead model keeps the hard work (design, tricky logic, integration) and hands small,
self-contained tasks to a faster assistant model, the way a senior developer splits work in a real team.

The assistant gets a fresh context with the task alone, may write only the files the lead named, cannot run
shell commands or delegate further, and reports back a summary, the files it changed and its last check run.
Its changes leave the lead's project unverified: the lead runs the checks before it may complete.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from petru.agent.state import Session
from petru.providers.base import ChatProvider
from petru.tools.base import Tool, ToolContext, ToolResult
from petru.tools.git import _run_git
from petru.tools.paths import OutsideProjectError, resolve_in_project
from petru.tools.registry import ToolRegistry
from petru.tui.port import ScriptedUI

LEAD_PROMPT = """You lead a small team. Read the task and its tests first, then, before you write the plan, \
decide once with choose_mode whether this project needs the team: choose team when the work splits into \
several files and some of them are simple pieces, solo when it is small or its parts call into each other \
so much that none can be written alone. Modules that only import shared models, errors or helpers are not \
tightly coupled: those shared files come first, and each module that uses them is a piece of its own. \
Working alone, you write everything yourself. Working as a team, split the work into pieces of one file \
each, and let the plan name the pieces you delegate. Hand every piece with a clear interface and little \
logic of its own (records and value types, exceptions, formatting and rendering, parsing helpers, simple \
validation) to the assistant with delegate, one piece per call, naming the exact types, signatures and \
messages it must provide and the files it should read. Keep only the hard parts yourself: the central \
algorithm, the integration and the final review. After each delegate call, read what changed and run \
run_checks before you build on it; if its work is wrong, fix it or delegate the fix with the failing output. \
You may create one new file yourself to start, then one more per piece you delegate; files that exist you \
may change at any time. The assistant sees nothing but the task and the files you list."""

WORKER_PROMPT = """You are an assistant on a team. The lead gave you one task: do exactly that task, nothing \
else. Write only the files the task lists, keep the names and signatures it asks for, run run_checks when \
you are done, and call task_complete with a two-line report: what you wrote and what the checks said. If the \
task cannot be done as written, call task_complete and say why."""

WORKER_TOOLS = (
    "read_file",
    "list_dir",
    "glob",
    "grep",
    "write_file",
    "edit_file",
    "run_checks",
    "task_complete",
)
WORKER_MAX_ITERATIONS = 30
WORKER_PORT_OFFSET = 10  # the assistant's server: next to the lead's port


def worker_request(task: str, files: list[str], read: list[str]) -> str:
    parts = [task.strip(), "", "Files you may write: " + ", ".join(files)]
    if read:
        parts.append("Read these first: " + ", ".join(read))
    return "\n".join(parts)


@dataclass
class Worker:
    """How to reach the assistant: a provider factory for a tier (its server starts on first use), its
    context, and which tier takes a piece (the specialist for the language of its files, once promoted)."""

    provider: Callable[[str], ChatProvider]
    ctx_tokens: int
    tier: str = "fast"
    max_iterations: int = WORKER_MAX_ITERATIONS
    tier_for: Callable[[list[str]], str] | None = None


class ScopedWrite(Tool):
    """A writing tool limited to the files the lead named."""

    def __init__(self, inner: Tool, allowed: set[Path]) -> None:
        self.inner, self.allowed = inner, allowed
        self.name, self.description, self.parameters = inner.name, inner.description, inner.parameters
        self.mutating, self.changes_files = inner.mutating, inner.changes_files

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            target = resolve_in_project(str(args.get("path", "")), ctx.project_root)
        except OutsideProjectError:
            target = None
        if target not in self.allowed:
            names = ", ".join(sorted(p.relative_to(ctx.project_root).as_posix() for p in self.allowed))
            return ToolResult(f"Not allowed: this task may only write {names}.", True)
        return self.inner.run(args, ctx)


def worker_registry(root: Path, files: list[str]) -> ToolRegistry:
    from petru.tools.registry import default_registry

    full = default_registry(False)
    allowed = set()
    for name in files:
        try:
            allowed.add(resolve_in_project(name, root))
        except OutsideProjectError:
            continue
    registry = ToolRegistry()
    for name in WORKER_TOOLS:
        tool = full.get(name)
        if tool is not None:
            registry.register(ScopedWrite(tool, allowed) if name in ("write_file", "edit_file") else tool)
    return registry


class Authors:
    """Who created and who then changed each file, in order. The tools keep it themselves: a summarised
    conversation loses the calls it would otherwise be read from."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, bool]] = []  # (lead or assistant, path, created)

    def record(self, who: str, path: str, created: bool) -> None:
        self.events.append((who, path, created))

    def credits(self) -> dict[str, str]:
        """Each file someone created: its author, and who changed it after (files given are left out)."""
        creators: dict[str, str] = {}
        changers: dict[str, set[str]] = {}
        for who, path, created in self.events:
            if path not in creators:
                if created:
                    creators[path], changers[path] = who, set()
            elif who != creators[path]:
                changers[path].add(who)
        later = {"lead": "extended by the assistant", "assistant": "revised by the lead"}
        return {
            path: f"{who}, {later[who]}" if changers[path] else who for path, who in sorted(creators.items())
        }


def _snapshot(root: Path, files: list[str]) -> dict[str, bytes | None]:
    """The content of each named file (None when absent), by its path relative to the project."""
    found = {}
    for name in files:
        try:
            path = resolve_in_project(name, root)
        except OutsideProjectError:
            continue
        found[path.relative_to(root).as_posix()] = path.read_bytes() if path.is_file() else None
    return found


class DelegateTool(Tool):
    name = "delegate"
    description = (
        "Hand one small, self-contained task to a faster assistant model with a fresh context: say exactly "
        "what to build (names, signatures, behaviour, tests) and list the files it may write. It returns its "
        "report, the files it changed and its last check run; run run_checks yourself before building on it."
    )
    mutating = True
    changes_files = True
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Complete instructions; the assistant sees nothing else",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "The only files it may create or change",
            },
            "read": {"type": "array", "items": {"type": "string"}, "description": "Files to read first"},
        },
        "required": ["task", "files"],
        "additionalProperties": False,
    }

    def __init__(self, worker: Worker) -> None:
        self.worker = worker
        self.calls = 0
        self.unavailable = False  # its server would not start: the lead finishes alone
        self.authors = Authors()

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        from petru.agent.loop import Agent

        files = [str(f) for f in args.get("files") or []]
        read = [str(f) for f in args.get("read") or []]
        tier = self.worker.tier_for(files) if self.worker.tier_for else self.worker.tier
        try:
            provider = self.worker.provider(tier)
        except Exception as exc:  # e.g. its model server would not start; nothing was delegated
            self.unavailable = True
            return ToolResult(f"The assistant could not start ({exc}). Work alone: write it yourself.", True)
        self.calls += 1
        session = Session(ctx.project_root, tier=tier, role=WORKER_PROMPT)
        agent = Agent(
            provider,
            worker_registry(ctx.project_root, files),
            ScriptedUI(),
            session,
            ctx.project_root,
            self.worker.ctx_tokens,
            False,
            max_iterations=self.worker.max_iterations,
            cancel=ctx.cancel,  # Esc stops the assistant too
            nested=True,
        )
        before = _snapshot(ctx.project_root, files)
        final = agent.run_turn(worker_request(str(args["task"]), files, read), quick=True)
        after = _snapshot(ctx.project_root, files)
        for path, old in before.items():
            if after.get(path) not in (old, None):
                self.authors.record("assistant", path, old is None)
        report = _last_tool_output(session, "task_complete") or final or "(no report)"
        checks = _last_tool_output(session, "run_checks") or "the assistant did not run the checks"
        changed = _run_git(["status", "--short"], ctx.project_root).output.strip() or "(nothing)"
        stop = f" (stopped: {agent.stop_reason})" if agent.stop_reason else ""
        return ToolResult(
            f"Assistant finished{stop}.\nReport: {report}\nChanged files:\n{changed}\n"
            f"Its last check run:\n{checks[-1500:]}"
        )


class ChooseModeTool(Tool):
    name = "choose_mode"
    description = (
        "Decide once, after reading the task and its tests, whether this project needs the team: 'team' when "
        "the work splits into several files and some are simple pieces the assistant can write from a clear "
        "interface, 'solo' when it is small or its parts call into each other so much that none can be "
        "written alone. Modules that only import shared models, errors or helpers are not tightly coupled."
    )
    parameters = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["team", "solo"]},
            "reason": {"type": "string", "description": "One sentence: why this project needs it or not"},
        },
        "required": ["mode", "reason"],
        "additionalProperties": False,
    }

    def __init__(self) -> None:
        self.mode: str | None = None
        self.reason: str | None = None

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if self.mode is not None:
            return ToolResult(f"You already chose {self.mode}; the choice is final.", True)
        mode = str(args.get("mode", ""))
        if mode not in ("team", "solo"):
            return ToolResult("mode must be team or solo.", True)
        self.mode, self.reason = mode, str(args.get("reason", ""))
        if mode == "solo":
            return ToolResult("Working alone: write every file yourself.")
        return ToolResult("Working as a team: write one file, then delegate a piece before each new one.")


TEST_NAME = re.compile(r"^test_|_test\.|\.test\.|\.spec\.", re.IGNORECASE)
CAMEL_TEST_NAME = re.compile(r"Tests?\.\w+$")  # LedgerTests.cs, ParserTest.java (capital T only)
TEST_DIRS = {"test", "tests", "__tests__", "spec"}


def is_test_file(relative: Path) -> bool:
    name = relative.name
    return bool(TEST_NAME.search(name) or CAMEL_TEST_NAME.search(name)) or any(
        part.lower() in TEST_DIRS for part in relative.parts[:-1]
    )


class LeadWrite(Tool):
    """The lead's write_file. Its first new file waits for choose_mode. Working as a team, a prompt alone
    does not make a model delegate, so the lead may create a new file only while it has created no more files
    than it has delegated pieces, plus one (it may start with the hard part). Files that exist stay free to
    change: integration and fixes are the lead's job, and so are its own tests, which it may always write."""

    def __init__(self, inner: Tool, delegate: DelegateTool, choice: ChooseModeTool) -> None:
        self.inner, self.delegate, self.choice, self.created = inner, delegate, choice, 0
        self.name, self.description, self.parameters = inner.name, inner.description, inner.parameters
        self.mutating, self.changes_files = inner.mutating, inner.changes_files

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        relative, existed = None, True
        try:
            target = resolve_in_project(str(args.get("path", "")), ctx.project_root)
            relative, existed = target.relative_to(ctx.project_root), target.exists()
            new = not existed and not is_test_file(relative)
        except OutsideProjectError, ValueError:
            new = False  # the inner tool reports it
        if new and self.choice.mode is None:
            return ToolResult(
                "Team mode: before you create files, decide with choose_mode whether this project needs the "
                "team (several files, some of them simple pieces) or you work alone (a small project).",
                True,
            )
        team = self.choice.mode == "team" and not self.delegate.unavailable
        if new and team and self.created > self.delegate.calls:
            return ToolResult(
                f"Team mode: you created {self.created} new file(s) yourself and delegated "
                f"{self.delegate.calls} piece(s). Hand this file, or another simple piece, to the assistant "
                "with delegate first; files that already exist you may change at any time.",
                True,
            )
        result = self.inner.run(args, ctx)
        if not result.is_error:
            if new:
                self.created += 1
            if relative is not None:
                self.delegate.authors.record("lead", relative.as_posix(), not existed)
        return result


class LeadPlan(Tool):
    """The lead's plan waits for choose_mode: a lead that planned first chose to match the plan it had
    written, not the project."""

    def __init__(self, inner: Tool, choice: ChooseModeTool) -> None:
        self.inner, self.choice = inner, choice
        self.name, self.description, self.parameters = inner.name, inner.description, inner.parameters

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if self.choice.mode is None:
            return ToolResult(
                "Team mode: decide with choose_mode first whether this project needs the team; the plan "
                "follows from that choice (as a team, it names the pieces you delegate).",
                True,
            )
        return self.inner.run(args, ctx)


class LeadEdit(Tool):
    """The lead's edit_file, recorded in the credits."""

    def __init__(self, inner: Tool, delegate: DelegateTool) -> None:
        self.inner, self.delegate = inner, delegate
        self.name, self.description, self.parameters = inner.name, inner.description, inner.parameters
        self.mutating, self.changes_files = inner.mutating, inner.changes_files

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        result = self.inner.run(args, ctx)
        if not result.is_error:
            try:
                target = resolve_in_project(str(args.get("path", "")), ctx.project_root)
                self.delegate.authors.record("lead", target.relative_to(ctx.project_root).as_posix(), False)
            except OutsideProjectError, ValueError:
                pass
        return result


def lead_registry(registry: ToolRegistry, worker: Worker) -> None:
    """Turn a full registry into the lead's: choose_mode, delegate, plan under LeadPlan, write_file under
    LeadWrite, edit_file recorded in the credits."""
    delegate, choice = DelegateTool(worker), ChooseModeTool()
    registry.register(choice)
    registry.register(delegate)
    plan, write, edit = registry.get("plan"), registry.get("write_file"), registry.get("edit_file")
    if plan is not None:
        registry.register(LeadPlan(plan, choice))
    if write is not None:
        registry.register(LeadWrite(write, delegate, choice))
    if edit is not None:
        registry.register(LeadEdit(edit, delegate))


def credits(registry: ToolRegistry) -> dict[str, str]:
    """Team mode: who wrote each file the lead or the assistant created."""
    delegate = registry.get("delegate")
    return delegate.authors.credits() if isinstance(delegate, DelegateTool) else {}


def start_task(registry: ToolRegistry) -> None:
    """A new task in the same session (the REPL): the lead chooses again and counts its files afresh."""
    choice, delegate, write = (registry.get(name) for name in ("choose_mode", "delegate", "write_file"))
    if isinstance(choice, ChooseModeTool):
        choice.mode, choice.reason = None, None
    if isinstance(delegate, DelegateTool):
        delegate.calls, delegate.unavailable, delegate.authors = 0, False, Authors()
    if isinstance(write, LeadWrite):
        write.created = 0


def _last_tool_output(session: Session, name: str) -> str:
    ids = {
        tc["id"]
        for message in session.messages
        if message.get("tool_calls")
        for tc in message["tool_calls"]
        if tc["function"]["name"] == name
    }
    outputs = [
        m["content"] for m in session.messages if m.get("role") == "tool" and m.get("tool_call_id") in ids
    ]
    return outputs[-1] if outputs else ""
