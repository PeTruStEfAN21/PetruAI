"""Live end-to-end harness: the real llama-server and model, a scripted user, a fresh project folder.

Run with: PETRU_E2E=1 uv run pytest -m e2e tests/e2e -v --timeout=1800
Env: PETRU_E2E_TIER (default|quality|fast, default "default"), PETRU_E2E_OFFLINE=1 forces the offline prompt.
Every run writes the full TaskResult (questions, tool calls, messages, checks) to tests/e2e/logs/<test>.json.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from petru.config import find_repo_root, load_config
from petru.offline import is_online
from petru.server import ServerManager
from petru.trajectory import TaskResult, TaskSpec, run_task

E2E = os.environ.get("PETRU_E2E") == "1"
TIER = os.environ.get("PETRU_E2E_TIER", "default")
FORCE_OFFLINE = os.environ.get("PETRU_E2E_OFFLINE") == "1"
LOG_DIR = Path(__file__).parent / "logs"


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
def live_task(live_server, tmp_path, request):
    """`run(prompt, answers)` builds the project in tmp_path with the real model; returns the TaskResult."""
    repo_root, cfg, base_url = live_server
    online = False if FORCE_OFFLINE else is_online()

    def run(prompt: str, answers: list[str], checks: list[str] | None = None) -> TaskResult:
        spec = TaskSpec(request.node.name, prompt, list(answers), list(checks or []), TIER)
        result = run_task(
            spec,
            repo_root=repo_root,
            project=tmp_path,
            ctx_tokens=cfg.tiers[TIER].ctx,
            base_url=base_url,
            online=online,
        )
        LOG_DIR.mkdir(exist_ok=True)
        result.save(LOG_DIR / f"{request.node.name}.json")
        return result

    return run


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8")
    return proc.stdout.strip()


def project_file(root: Path, name: str) -> Path | None:
    """`name` in the root or one level down (the model sometimes scaffolds into a subfolder)."""
    found = sorted(root.glob(name)) + sorted(root.glob(f"*/{name}"))
    return found[0] if found else None


def assert_committed(root: Path) -> None:
    assert _git(root, "log", "--oneline"), "the project has no commits"
    assert _git(root, "status", "--porcelain") == "", "the working tree is not clean after the commit"
