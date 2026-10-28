"""Run one scripted task through the agent and export the transcript: training data and evaluation share it.

python -m petru.trajectory tasks/python_hello.toml --base-url http://127.0.0.1:8080/v1 --out result.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from petru.agent.context import transcript_tokens
from petru.agent.loop import Agent
from petru.agent.state import Phase, Session
from petru.agent.team import LEAD_PROMPT, WORKER_PORT_OFFSET, Worker, credits, lead_registry
from petru.config import find_repo_root, load_config
from petru.providers.base import ChatProvider
from petru.providers.openai_compat import OpenAICompatProvider
from petru.server import ServerManager
from petru.tools.base import Tool, ToolContext, ToolResult
from petru.tools.checks import detect_checks, find_project_dirs
from petru.tools.git import _run_git, ensure_repo
from petru.tools.registry import default_registry
from petru.tools.shell import run_shell
from petru.tui.port import ScriptedUI

FALLBACK_ANSWER = "Your choice; keep it simple and use only what is already installed."
CONTINUE_PROMPT = (
    "Continue with the confirmed plan using tools. Run run_checks, fix failures, commit when green, "
    "then call task_complete."
)
CHECK_TIMEOUT_S = 600


@dataclass
class TaskSpec:
    name: str
    prompt: str
    answers: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    tier: str = "quality"
    seed: Path | None = None  # files copied into the project and committed before the agent starts
    protect: list[str] = field(default_factory=list)  # seed files put back before the final checks
    setup: list[str] = field(default_factory=list)  # commands run once the seed is in place (dependencies)
    forbid: list[str] = field(default_factory=list)  # globs of test config the agent may not add
    solution: list[str] = field(default_factory=list)  # set: only these files reach a fresh final check


def load_task(path: Path) -> TaskSpec:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return TaskSpec(
        name=str(data.get("name") or path.stem),
        prompt=str(data["prompt"]),
        answers=[str(a) for a in data.get("answers", [])],
        checks=[str(c) for c in data.get("checks", [])],
        tier=str(data.get("tier", "quality")),
        seed=path.parent / data["seed"] if data.get("seed") else None,
        protect=[str(p) for p in data.get("protect", [])],
        setup=[str(c) for c in data.get("setup", [])],
        forbid=[str(g) for g in data.get("forbid", [])],
        solution=[str(f) for f in data.get("solution", [])],
    )


def plant_seed(seed: Path, project: Path) -> None:
    """The exercise scaffold as the project's first commit, so the agent starts from a clean tree."""
    shutil.copytree(seed, project, dirs_exist_ok=True)
    _run_git(["add", "-A"], project)
    _run_git(["commit", "-q", "-m", "Exercise scaffold"], project)


def run_setup(spec: TaskSpec, project: Path) -> tuple[bool, str]:
    """The task's setup commands (installing dependencies) in order; stops at the first that fails."""
    reports = []
    for cmd in spec.setup:
        result = run_shell(cmd, project, timeout_s=CHECK_TIMEOUT_S)
        reports.append(f"[{'FAIL' if result.is_error else 'OK'}] {cmd}\n{result.output}")
        if result.is_error:
            return False, "setup failed:\n" + "\n\n".join(reports)
    return True, "\n\n".join(reports)


def restore_protected(spec: TaskSpec, project: Path) -> None:
    """Put the original tests and their configuration back, and drop test configuration the agent added: a
    task passes on its own tests, not on ones the agent rewrote, skipped or deselected."""
    for rel in spec.protect:
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(spec.seed / rel, target)
    for pattern in spec.forbid:
        for path in project.glob(pattern):
            rel = path.relative_to(project)
            if path.is_file() and ".git" not in rel.parts and not (spec.seed / rel).exists():
                path.unlink()


@dataclass
class TaskResult:
    name: str
    passed: bool
    seconds: float
    tokens: int
    stop_reason: str | None
    messages: list[dict]
    tools: list[dict]
    check_output: str
    extra_turns: int
    delegations: int = 0  # team mode: delegate calls, counted by the tool itself
    team_choice: str | None = None  # team mode: what the lead chose with choose_mode (team, solo, or none)
    team_reason: str | None = None  # team mode: the reason the lead gave for that choice
    authors: dict[str, str] = field(default_factory=dict)  # team mode: who wrote each file, kept by the tools

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> TaskResult:
        return cls(**json.loads(path.read_text(encoding="utf-8")))


class TaskUI(ScriptedUI):
    """Scripted user for unattended runs: confirms everything, answers sensibly when the script runs out."""

    def __init__(self, answers: list[str]) -> None:
        super().__init__(answers, confirm="always", plan_action="confirm")

    def next_answer(self) -> str:
        return self._answers.pop(0) if self._answers else FALLBACK_ANSWER

    def ask(self, question: str, options: list[str] | None) -> str:
        if not self._answers:
            self.questions.append((question, options))
            return FALLBACK_ANSWER
        return super().ask(question, options)


def run_checks_for(project: Path, extra: list[str]) -> tuple[bool, str]:
    """Every detected check (root or single nested project) plus the task's own commands; all must exit 0."""
    reports: list[str] = []
    ok = True
    for directory in find_project_dirs(project):
        for cmd in detect_checks(directory):
            result = run_shell(cmd, directory, timeout_s=CHECK_TIMEOUT_S)
            reports.append(f"[{'FAIL' if result.is_error else 'PASS'}] {cmd}\n{result.output}")
            ok = ok and not result.is_error
    for cmd in extra:
        result = run_shell(cmd, project, timeout_s=CHECK_TIMEOUT_S)
        reports.append(f"[{'FAIL' if result.is_error else 'PASS'}] {cmd}\n{result.output}")
        ok = ok and not result.is_error
    if not reports:  # nothing verified the work: a task that asked for tests did not get any
        return False, "no checks found: the project has no tests and the task lists no commands"
    return ok, "\n\n".join(reports)


@contextmanager
def isolated_home() -> Iterator[Path]:
    """Point PETRU_HOME at a throwaway folder outside the project for the duration, then restore it."""
    previous = os.environ.get("PETRU_HOME")
    with tempfile.TemporaryDirectory(prefix="petru-home-", ignore_cleanup_errors=True) as tmp:
        os.environ["PETRU_HOME"] = tmp
        try:
            yield Path(tmp)
        finally:
            if previous is None:
                os.environ.pop("PETRU_HOME", None)
            else:
                os.environ["PETRU_HOME"] = previous


def verify_task(spec: TaskSpec, project: Path, solution: Path | None) -> tuple[bool, str]:
    """The task's checks on its seed with `solution` copied on top, no model involved: validates a task."""
    project.mkdir(parents=True, exist_ok=True)
    ensure_repo(project)
    if spec.seed is not None:
        plant_seed(spec.seed, project)
    ready, setup_output = run_setup(spec, project)
    if not ready:
        return False, setup_output
    if solution is not None:
        shutil.copytree(solution, project, dirs_exist_ok=True)
    return run_checks_for(project, spec.checks)


def check_solution(spec: TaskSpec, project: Path) -> tuple[bool, str]:
    """Exercism's rule: only the solution files leave the agent's project. The final check runs on a fresh
    copy of the seed with them on top, so no test, test configuration or extra file of the agent counts."""
    with tempfile.TemporaryDirectory(prefix="petru-final-", ignore_cleanup_errors=True) as tmp:
        solution = Path(tmp) / "solution"
        solution.mkdir()
        for rel in spec.solution:
            if (project / rel).is_file():
                (solution / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(project / rel, solution / rel)
        return verify_task(spec, Path(tmp) / "project", solution)


class ChoiceMade(KeyboardInterrupt):
    """Ends a choice-only run the way Ctrl+C ends a turn: the lead has chosen, nothing more is needed."""


class StopAfterChoice(Tool):
    """choose_mode in a choice-only run: a valid choice is recorded by the inner tool, then the run ends."""

    def __init__(self, inner: Tool) -> None:
        self.inner = inner
        self.name, self.description, self.parameters = inner.name, inner.description, inner.parameters

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        result = self.inner.run(args, ctx)
        if not result.is_error:
            raise ChoiceMade
        return result


# A turn that ended on the iteration limit is one a user answers with "continue"; a large project ends many.
GOES_ON = (None, "iteration limit")


def run_task(
    spec: TaskSpec,
    *,
    repo_root: Path,
    project: Path,
    ctx_tokens: int,
    base_url: str | None = None,
    provider: ChatProvider | None = None,
    max_extra_turns: int = 10,
    online: bool = False,
    max_iterations: int = 60,
    worker: Worker | None = None,
    choice_only: bool = False,
    time_limit_s: float | None = None,
) -> TaskResult:
    """One task as a user would live it: the prompt, answers to questions the model wrote as plain text
    instead of calling ask_user, and 'continue' while it stops talking (or hits the iteration limit) in BUILD
    before task_complete. With `choice_only`, a team run ends as soon as the lead has chosen its mode; with
    `time_limit_s`, the run stops on its own when that time is up, and its transcript is kept."""
    if provider is None:
        if base_url is None:
            raise ValueError("run_task needs a provider or a base_url")
        provider = OpenAICompatProvider(base_url)
    project.mkdir(parents=True, exist_ok=True)
    ensure_repo(project)
    if spec.seed is not None:
        plant_seed(spec.seed, project)
    run_setup(spec, project)  # a failed install shows up in the agent's own check runs
    ui = TaskUI(list(spec.answers))
    session = Session(project, tier=spec.tier, role=LEAD_PROMPT if worker else "")
    registry = default_registry(online)
    if worker is not None:  # team mode: the model leads and delegates small tasks
        lead_registry(registry, worker)
    choice = registry.get("choose_mode")
    if choice_only and choice is not None:
        registry.register(StopAfterChoice(choice))
    started = time.monotonic()
    deadline = None if time_limit_s is None else started + time_limit_s
    agent = Agent(
        provider, registry, ui, session, repo_root, ctx_tokens, online, max_iterations=max_iterations,
        deadline=deadline,
    )  # fmt: skip
    extra = 0
    with isolated_home():  # scripted runs must never write into the user's real global memory
        agent.run_turn(spec.prompt)
        while session.phase is not Phase.IDLE and agent.stop_reason in GOES_ON and extra < max_extra_turns:
            if session.phase is Phase.DESIGN:
                message = f"{ui.next_answer()} (Use the ask_user tool for further questions, then call plan.)"
            else:
                message = CONTINUE_PROMPT
            extra += 1
            agent.run_turn(message)
    completed = session.phase is Phase.IDLE and agent.stop_reason in GOES_ON
    if completed and spec.seed is not None and spec.solution:
        ok, output = check_solution(spec, project)
    elif completed:
        if spec.seed is not None:
            restore_protected(spec, project)
        ok, output = run_checks_for(project, spec.checks)
    else:
        ok, output = False, f"task did not complete (phase={session.phase.value}, stop={agent.stop_reason})"
    return TaskResult(
        name=spec.name,
        passed=ok,
        seconds=round(time.monotonic() - started, 1),
        tokens=transcript_tokens(session.messages, provider),
        stop_reason=agent.stop_reason,
        messages=session.messages,
        tools=registry.schemas(),
        check_output=output,
        extra_turns=extra,
        delegations=getattr(registry.get("delegate"), "calls", 0),
        team_choice=getattr(choice, "mode", None),
        team_reason=getattr(choice, "reason", None),
        authors=credits(registry),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one task through the agent and save the transcript.")
    parser.add_argument("task", type=Path)
    parser.add_argument("--base-url", default=None, help="running llama-server (otherwise one is started)")
    parser.add_argument("--tier", default=None, help="tier override (model and context size)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--project", type=Path, default=None, help="project folder (default: a fresh temp dir)"
    )
    parser.add_argument("--max-extra-turns", type=int, default=10)
    parser.add_argument(
        "--team", action="store_true", help="lead a team: delegate small tasks to --worker-tier"
    )
    parser.add_argument("--worker-tier", default="fast", help="the assistant model in team mode")
    parser.add_argument("--worker-base-url", default=None, help="running llama-server of the assistant")
    parser.add_argument(
        "--time-limit", type=float, default=None, help="seconds after which the run stops and saves itself"
    )
    parser.add_argument(
        "--choice-only", action="store_true", help="team mode: stop once the lead has chosen team or solo"
    )
    parser.add_argument(
        "--verify-with",
        type=Path,
        default=None,
        help="no model: run the checks on the seed plus this solution",
    )
    args = parser.parse_args(argv)
    spec = load_task(args.task)
    if args.verify_with is not None:
        return _verify_cli(spec, args)
    tier = args.tier or spec.tier
    repo_root = find_repo_root(Path(__file__))
    cfg = load_config(repo_root)
    if tier not in cfg.tiers:
        print(f"unknown tier {tier!r}; tiers: {', '.join(cfg.tiers)}", file=sys.stderr)
        return 2
    project = args.project or Path(tempfile.mkdtemp(prefix=f"petru-{spec.name}-"))
    manager = None
    base_url = args.base_url
    if base_url is None:
        manager = ServerManager(cfg)
        base_url = manager.ensure_running(tier)
    worker, worker_manager = None, None
    if args.team:
        worker_url = args.worker_base_url
        if worker_url is None:  # a second server next to the lead's, on its own port
            worker_manager = ServerManager(replace(cfg, port=cfg.port + WORKER_PORT_OFFSET))
            worker_url = worker_manager.ensure_running(args.worker_tier)
        worker = Worker(
            provider=lambda tier: OpenAICompatProvider(worker_url),
            ctx_tokens=cfg.tiers[args.worker_tier].ctx,
            tier=args.worker_tier,
        )
    try:
        result = run_task(
            spec,
            repo_root=repo_root,
            project=project,
            ctx_tokens=cfg.tiers[tier].ctx,
            max_iterations=cfg.tiers[tier].max_iterations,
            base_url=base_url,
            max_extra_turns=args.max_extra_turns,
            worker=worker,
            choice_only=args.choice_only,
            time_limit_s=args.time_limit,
        )
    finally:
        for running in (manager, worker_manager):
            if running is not None:
                running.stop()
    result.save(args.out)
    status = "PASS" if result.passed else "FAIL"
    print(f"{spec.name}: {status} in {result.seconds}s, {result.tokens} tokens -> {args.out}")
    return 0 if result.passed else 1


def _verify_cli(spec: TaskSpec, args: argparse.Namespace) -> int:
    started = time.monotonic()
    project = args.project or Path(tempfile.mkdtemp(prefix=f"petru-verify-{spec.name}-"))
    ok, output = verify_task(spec, project, args.verify_with)
    data = {
        "name": spec.name,
        "passed": ok,
        "seconds": round(time.monotonic() - started, 1),
        "check_output": output,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{spec.name}: {'PASS' if ok else 'FAIL'} in {data['seconds']}s (verify)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
