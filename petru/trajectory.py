"""Run one scripted task through the agent and export the transcript: training data and evaluation share it.

python -m petru.trajectory tasks/python_hello.toml --base-url http://127.0.0.1:8080/v1 --out result.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from petru.agent.context import transcript_tokens
from petru.agent.loop import Agent
from petru.agent.state import Phase, Session
from petru.config import find_repo_root, load_config
from petru.providers.base import ChatProvider
from petru.providers.openai_compat import OpenAICompatProvider
from petru.server import ServerManager
from petru.tools.checks import detect_checks, find_project_dirs
from petru.tools.git import ensure_repo
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


def load_task(path: Path) -> TaskSpec:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return TaskSpec(
        name=str(data.get("name") or path.stem),
        prompt=str(data["prompt"]),
        answers=[str(a) for a in data.get("answers", [])],
        checks=[str(c) for c in data.get("checks", [])],
        tier=str(data.get("tier", "quality")),
    )


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
) -> TaskResult:
    """One task as a user would live it: the prompt, answers to questions the model wrote as plain text
    instead of calling ask_user, and 'continue' while it stops talking in BUILD before task_complete."""
    if provider is None:
        if base_url is None:
            raise ValueError("run_task needs a provider or a base_url")
        provider = OpenAICompatProvider(base_url)
    project.mkdir(parents=True, exist_ok=True)
    ensure_repo(project)
    ui = TaskUI(list(spec.answers))
    session = Session(project, tier=spec.tier)
    registry = default_registry(online)
    agent = Agent(provider, registry, ui, session, repo_root, ctx_tokens, online)
    started = time.monotonic()
    extra = 0
    with isolated_home():  # scripted runs must never write into the user's real global memory
        agent.run_turn(spec.prompt)
        while session.phase is not Phase.IDLE and agent.stop_reason is None and extra < max_extra_turns:
            if session.phase is Phase.DESIGN:
                message = f"{ui.next_answer()} (Use the ask_user tool for further questions, then call plan.)"
            else:
                message = CONTINUE_PROMPT
            extra += 1
            agent.run_turn(message)
    completed = session.phase is Phase.IDLE and agent.stop_reason is None
    if completed:
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
    args = parser.parse_args(argv)
    spec = load_task(args.task)
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
    try:
        result = run_task(
            spec,
            repo_root=repo_root,
            project=project,
            ctx_tokens=cfg.tiers[tier].ctx,
            base_url=base_url,
            max_extra_turns=args.max_extra_turns,
        )
    finally:
        if manager is not None:
            manager.stop()
    result.save(args.out)
    status = "PASS" if result.passed else "FAIL"
    print(f"{spec.name}: {status} in {result.seconds}s, {result.tokens} tokens -> {args.out}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
