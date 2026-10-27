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

LEAD_PROMPT = """You lead a small team and you are expected to use it. Before you write code, read the \
tests and split the work into pieces of one file each. Hand every piece with a clear interface and little \
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


def worker_request(task: str, files: list[str], read: list[str]) -> str:
    parts = [task.strip(), "", "Files you may write: " + ", ".join(files)]
    if read:
        parts.append("Read these first: " + ", ".join(read))
    return "\n".join(parts)


@dataclass
class Worker:
    """How to reach the assistant model: a provider factory (its server starts on first use), its context."""

    provider: Callable[[], ChatProvider]
    ctx_tokens: int
    tier: str = "fast"
    max_iterations: int = WORKER_MAX_ITERATIONS


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

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        from petru.agent.loop import Agent

        self.calls += 1
        files = [str(f) for f in args.get("files") or []]
        read = [str(f) for f in args.get("read") or []]
        session = Session(ctx.project_root, tier=self.worker.tier, role=WORKER_PROMPT)
        agent = Agent(
            self.worker.provider(),
            worker_registry(ctx.project_root, files),
            ScriptedUI(),
            session,
            ctx.project_root,
            self.worker.ctx_tokens,
            False,
            max_iterations=self.worker.max_iterations,
        )
        final = agent.run_turn(worker_request(str(args["task"]), files, read), quick=True)
        report = _last_tool_output(session, "task_complete") or final or "(no report)"
        checks = _last_tool_output(session, "run_checks") or "the assistant did not run the checks"
        changed = _run_git(["status", "--short"], ctx.project_root).output.strip() or "(nothing)"
        stop = f" (stopped: {agent.stop_reason})" if agent.stop_reason else ""
        return ToolResult(
            f"Assistant finished{stop}.\nReport: {report}\nChanged files:\n{changed}\n"
            f"Its last check run:\n{checks[-1500:]}"
        )


TEST_NAME = re.compile(r"^test_|_test\.|\.test\.|\.spec\.", re.IGNORECASE)
CAMEL_TEST_NAME = re.compile(r"Tests?\.\w+$")  # LedgerTests.cs, ParserTest.java (capital T only)
TEST_DIRS = {"test", "tests", "__tests__", "spec"}


def is_test_file(relative: Path) -> bool:
    name = relative.name
    return bool(TEST_NAME.search(name) or CAMEL_TEST_NAME.search(name)) or any(
        part.lower() in TEST_DIRS for part in relative.parts[:-1]
    )


class LeadWrite(Tool):
    """The lead's write_file: a prompt alone does not make a model delegate, so the lead may create a new
    file only while it has created no more files than it has delegated pieces, plus one (it may start with
    the hard part). Files that exist stay free to change: integration and fixes are the lead's job, and so
    are its own tests, which it may always write."""

    def __init__(self, inner: Tool, delegate: DelegateTool) -> None:
        self.inner, self.delegate, self.created = inner, delegate, 0
        self.name, self.description, self.parameters = inner.name, inner.description, inner.parameters
        self.mutating, self.changes_files = inner.mutating, inner.changes_files

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        try:
            target = resolve_in_project(str(args.get("path", "")), ctx.project_root)
            new = not target.exists() and not is_test_file(target.relative_to(ctx.project_root))
        except OutsideProjectError, ValueError:
            new = False  # the inner tool reports it
        if new and self.created > self.delegate.calls:
            return ToolResult(
                f"Team mode: you created {self.created} new file(s) yourself and delegated "
                f"{self.delegate.calls} piece(s). Hand this file, or another simple piece, to the assistant "
                "with delegate first; files that already exist you may change at any time.",
                True,
            )
        result = self.inner.run(args, ctx)
        if new and not result.is_error:
            self.created += 1
        return result


def lead_registry(registry: ToolRegistry, worker: Worker) -> None:
    """Turn a full registry into the lead's: the delegate tool, and write_file under LeadWrite."""
    delegate = DelegateTool(worker)
    registry.register(delegate)
    write = registry.get("write_file")
    if write is not None:
        registry.register(LeadWrite(write, delegate))


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
