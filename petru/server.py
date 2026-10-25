"""Start, reuse and stop the local llama-server for a model tier."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable

from petru.config import COMMON_SERVER_ARGS, Config, Tier

HttpGet = Callable[[str, float], tuple[int, str]]


class ServerStartError(RuntimeError):
    """llama-server could not be started or is not usable."""


def build_server_command(cfg: Config, tier: Tier) -> list[str]:
    return [
        str(cfg.server_exe),
        "-m",
        str(cfg.models_dir / tier.model_file),
        "-c",
        str(tier.ctx),
        *COMMON_SERVER_ARGS,
        "--port",
        str(cfg.port),
        "--host",
        "127.0.0.1",
        *tier.extra_args,
    ]


def _default_http_get(url: str, timeout: float) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


class ServerManager:
    def __init__(
        self,
        cfg: Config,
        spawn: Callable[..., subprocess.Popen] = subprocess.Popen,
        http_get: HttpGet = _default_http_get,
        startup_timeout_s: float = 180.0,
        poll_s: float = 0.5,
    ) -> None:
        self.cfg = cfg
        self._spawn = spawn
        self._http_get = http_get
        self._startup_timeout_s = startup_timeout_s
        self._poll_s = poll_s
        self._proc: subprocess.Popen | None = None
        self._stderr_tail: deque[str] = deque(maxlen=200)
        self._drain: threading.Thread | None = None
        self.current_tier: str | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.cfg.port}/v1"

    def _get(self, path: str) -> tuple[int, str]:
        try:
            return self._http_get(f"http://127.0.0.1:{self.cfg.port}{path}", 2.0)
        except Exception:
            return 0, ""

    def is_healthy(self) -> bool:
        return self._get("/health")[0] == 200

    def _running_model(self) -> str:
        status, body = self._get("/v1/models")
        if status != 200:
            return ""
        try:
            data = json.loads(body).get("data", [])
        except json.JSONDecodeError, AttributeError:
            return ""
        return str(data[0].get("id", "")) if data else ""

    def _owns_live_process(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure_running(self, tier_name: str) -> str:
        tier = self.cfg.tiers[tier_name]
        if self._owns_live_process():
            if self.current_tier == tier_name and self.is_healthy():
                return self.base_url
            self.stop()
        elif self.is_healthy():
            model = self._running_model()
            if tier.model_file in model:
                self.current_tier = tier_name
                return self.base_url
            raise ServerStartError(
                f"Port {self.cfg.port} is already serving {model or 'another model'}; "
                f"stop it or switch to its tier before starting {tier_name!r}."
            )
        self._start(tier)
        self.current_tier = tier_name
        return self.base_url

    def _start(self, tier: Tier) -> None:
        cmd = build_server_command(self.cfg, tier)
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
        self._stderr_tail.clear()
        self._proc = self._spawn(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags)
        if getattr(self._proc, "stderr", None) is not None:
            self._drain = threading.Thread(target=self._drain_stderr, args=(self._proc.stderr,), daemon=True)
            self._drain.start()
        deadline = time.monotonic() + self._startup_timeout_s
        while time.monotonic() < deadline:
            code = self._proc.poll()
            if code is not None:
                raise ServerStartError(f"llama-server exited with code {code}\n{self._tail()}")
            if self.is_healthy():
                return
            time.sleep(self._poll_s)
        self.stop()
        raise ServerStartError(
            f"llama-server did not become healthy within {self._startup_timeout_s:g}s\n{self._tail()}"
        )

    def _drain_stderr(self, stream) -> None:
        for raw in iter(stream.readline, b""):
            self._stderr_tail.append(raw.decode("utf-8", errors="replace").rstrip())

    def _tail(self, lines: int = 20) -> str:
        if self._drain is not None:
            self._drain.join(timeout=0.5)
        return "\n".join(list(self._stderr_tail)[-lines:])

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        self.current_tier = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
