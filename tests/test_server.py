import io
import json

import pytest

from petru.config import load_config
from petru.server import ServerManager, ServerStartError, build_server_command

MODELS_9B = json.dumps({"data": [{"id": "C:/x/infra/llama.cpp/models/Qwen3.5-9B.IQ4_XS.gguf"}]})


class FakeProc:
    def __init__(self, stderr_lines=()):
        self.terminated = False
        self.returncode = None
        self.stderr = io.BytesIO("".join(f"{line}\n" for line in stderr_lines).encode())

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.terminated = True
        self.returncode = -9


@pytest.fixture
def cfg(tmp_path):
    return load_config(repo_root=tmp_path)


def test_build_command_default_tier(cfg):
    cmd = build_server_command(cfg, cfg.tiers["default"])
    assert cmd[0] == str(cfg.server_exe)
    assert cmd[cmd.index("-m") + 1] == str(cfg.models_dir / "Qwen3.5-9B.IQ4_XS.gguf")
    for flag in ("--jinja", "--flash-attn", "-ngl", "--cache-type-k", "--cache-type-v", "--port", "--host"):
        assert flag in cmd
    assert cmd[cmd.index("-c") + 1] == "16384"
    assert cmd[cmd.index("--port") + 1] == "8080"
    assert "--cpu-moe" in build_server_command(cfg, cfg.tiers["quality"])


def test_ensure_running_spawns_then_waits_for_health(cfg):
    calls, health = [], iter([503, 503, 200])
    mgr = ServerManager(
        cfg,
        spawn=lambda cmd, **kw: calls.append(cmd) or FakeProc(),
        http_get=lambda url, timeout: (next(health), ""),
        poll_s=0.01,
    )
    assert mgr.ensure_running("default") == "http://127.0.0.1:8080/v1"
    assert len(calls) == 1 and mgr.current_tier == "default"


def test_switching_tier_stops_previous(cfg):
    procs = []
    mgr = ServerManager(
        cfg,
        spawn=lambda cmd, **kw: procs.append(FakeProc()) or procs[-1],
        http_get=lambda url, timeout: (200 if procs else 503, ""),
        poll_s=0.01,
    )
    mgr.ensure_running("default")
    mgr.ensure_running("quality")
    assert procs[0].terminated and len(procs) == 2 and mgr.current_tier == "quality"


def test_same_tier_is_reused_without_respawn(cfg):
    procs = []
    mgr = ServerManager(
        cfg,
        spawn=lambda cmd, **kw: procs.append(FakeProc()) or procs[-1],
        http_get=lambda url, timeout: (200 if procs else 503, ""),
        poll_s=0.01,
    )
    mgr.ensure_running("default")
    mgr.ensure_running("default")
    assert len(procs) == 1


def test_reuses_external_server_with_same_model(cfg):
    spawned = []
    mgr = ServerManager(
        cfg,
        spawn=lambda cmd, **kw: spawned.append(cmd) or FakeProc(),
        http_get=lambda url, timeout: (200, MODELS_9B if url.endswith("/v1/models") else ""),
    )
    assert mgr.ensure_running("default") == "http://127.0.0.1:8080/v1"
    assert spawned == [] and mgr.current_tier == "default"


def test_external_server_with_other_model_raises(cfg):
    mgr = ServerManager(
        cfg,
        spawn=lambda cmd, **kw: FakeProc(),
        http_get=lambda url, timeout: (200, MODELS_9B if url.endswith("/v1/models") else ""),
    )
    with pytest.raises(ServerStartError, match="Qwen3.5-9B"):
        mgr.ensure_running("quality")


def test_startup_timeout_raises_with_stderr(cfg):
    mgr = ServerManager(
        cfg,
        spawn=lambda cmd, **kw: FakeProc(stderr_lines=["error: model not found"]),
        http_get=lambda url, timeout: (503, ""),
        startup_timeout_s=0.3,
        poll_s=0.05,
    )
    with pytest.raises(ServerStartError, match="model not found"):
        mgr.ensure_running("default")
