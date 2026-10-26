"""Live end-to-end harness: the real llama-server and model, a scripted user, a fresh project folder.

Run with: PETRU_E2E=1 uv run pytest -m e2e tests/e2e -v --timeout=1800
Env: PETRU_E2E_TIER (default|quality|fast, default "default"), PETRU_E2E_OFFLINE=1 forces the offline prompt.
Every run writes a JSON transcript to tests/e2e/logs/<test name>.json (gitignored).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from petru.agent.loop import Agent
from petru.agent.state import Phase, Session
from petru.config import find_repo_root, load_config
from petru.offline import is_online
from petru.providers.openai_compat import OpenAICompatProvider
from petru.server import ServerManager
from petru.tools.checks import detect_checks, find_project_dirs
from petru.tools.git import ensure_repo
from petru.tools.registry import default_registry
from petru.tools.shell import run_shell
from petru.tui.port import ScriptedUI

E2E = os.environ.get("PETRU_E2E") == "1"
TIER = os.environ.get("PETRU_E2E_TIER", "default")
FORCE_OFFLINE = os.environ.get("PETRU_E2E_OFFLINE") == "1"
LOG_DIR = Path(__file__).parent / "logs"
FALLBACK_ANSWER = "Your choice; keep it simple and use only what is already installed."


CONTINUE_PROMPT = (
    "Continue with the confirmed plan using tools. Run run_checks, fix failures, commit when green, "
    "then call task_complete."
)
MAX_EXTRA_TURNS = 10


class DemoUI(ScriptedUI):
    """ScriptedUI that keeps answering sensibly when the model asks more questions than scripted."""

    def __init__(self, answers: list[str], **kwargs) -> None:
        super().__init__(answers, **kwargs)
        self.extra_turns: list[str] = []

    def next_answer(self) -> str:
        return self._answers.pop(0) if self._answers else FALLBACK_ANSWER

    def ask(self, question: str, options: list[str] | None) -> str:
        if not self._answers:
            self.questions.append((question, options))
            return FALLBACK_ANSWER
        return super().ask(question, options)


def run_demo(agent: Agent, prompt: str) -> str:
    """One demo as a user would live it: the first prompt, then answers to questions the model wrote as plain
    text instead of calling ask_user, then 'continue' while it stops talking in BUILD before task_complete."""
    ui: DemoUI = agent.ui  # type: ignore[assignment]
    text = agent.run_turn(prompt)
    while agent.session.phase is not Phase.IDLE and agent.stop_reason is None:
        if len(ui.extra_turns) >= MAX_EXTRA_TURNS:
            break
        if agent.session.phase is Phase.DESIGN:
            message = f"{ui.next_answer()} (Use the ask_user tool for further questions, then call plan.)"
        else:
            message = CONTINUE_PROMPT
        ui.extra_turns.append(message)
        text = agent.run_turn(message)
    return text


@pytest.fixture(scope="session")
def live_server():
    if not E2E:
        pytest.skip("set PETRU_E2E=1 to run the live demos")
    repo_root = find_repo_root(Path(__file__))
    cfg = load_config(repo_root)
    manager = ServerManager(cfg)
    base_url = manager.ensure_running(TIER)
    yield repo_root, cfg, base_url
    manager.stop()


@pytest.fixture
def live_agent(live_server, tmp_path, request):
    repo_root, cfg, base_url = live_server
    ensure_repo(tmp_path)
    online = False if FORCE_OFFLINE else is_online()
    made: list[tuple[Agent, DemoUI, float]] = []

    def make(answers: list[str]) -> Agent:
        ui = DemoUI(answers, confirm="always", plan_action="confirm")
        session = Session(tmp_path, tier=TIER)
        agent = Agent(
            provider=OpenAICompatProvider(base_url),
            registry=default_registry(online),
            ui=ui,
            session=session,
            repo_root=repo_root,
            ctx_tokens=cfg.tiers[TIER].ctx,
            online=online,
        )
        made.append((agent, ui, time.monotonic()))
        return agent

    yield make

    LOG_DIR.mkdir(exist_ok=True)
    for agent, ui, started in made:
        log = {
            "test": request.node.name,
            "tier": TIER,
            "online": online,
            "seconds": round(time.monotonic() - started),
            "phase": agent.session.phase.value,
            "stop_reason": agent.stop_reason,
            "questions": ui.questions,
            "extra_turns": ui.extra_turns,
            "notices": ui.notices,
            "tool_events": [[str(x) for x in event] for event in ui.tool_events],
            "messages": agent.session.messages,
        }
        path = LOG_DIR / f"{request.node.name}.json"
        path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip()


def assert_checks_pass(root: Path) -> None:
    """Every detected check passes, in the root or in a single nested project the model created."""
    project_dirs = find_project_dirs(root)
    assert project_dirs, "no checks detected in the generated project"
    for project in project_dirs:
        for cmd in detect_checks(project):
            result = run_shell(cmd, project, timeout_s=600)
            assert not result.is_error, f"{cmd} failed in {project.name}:\n{result.output}"


def project_file(root: Path, name: str) -> Path | None:
    """`name` in the root or one level down (the model sometimes scaffolds into a subfolder)."""
    found = sorted(root.glob(name)) + sorted(root.glob(f"*/{name}"))
    return found[0] if found else None


def assert_committed(root: Path) -> None:
    assert _git(root, "log", "--oneline"), "the project has no commits"
    assert _git(root, "status", "--porcelain") == "", "the working tree is not clean after the commit"
