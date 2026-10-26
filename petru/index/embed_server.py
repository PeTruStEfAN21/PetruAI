"""A second llama-server for embeddings (EmbeddingGemma 2), on the CPU so it never competes with the chat
model for the 6 GB of VRAM."""

from __future__ import annotations

import subprocess
import time
import urllib.request
from collections.abc import Callable

from petru.config import Config

EMBED_MODEL = "embeddinggemma-2-Q8_0.gguf"
EMBED_PORT = 8082
EMBED_URL = f"http://127.0.0.1:{EMBED_PORT}/v1"


def embed_server_healthy(timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{EMBED_PORT}/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


class EmbedServer:
    def __init__(
        self,
        cfg: Config,
        spawn: Callable[..., subprocess.Popen] = subprocess.Popen,
        healthy: Callable[[], bool] = embed_server_healthy,
        startup_timeout_s: float = 90.0,
        poll_s: float = 0.5,
    ) -> None:
        self.cfg = cfg
        self._spawn = spawn
        self._healthy = healthy
        self._timeout = startup_timeout_s
        self._poll = poll_s
        self._proc = None

    def command(self) -> list[str]:
        return [
            str(self.cfg.server_exe), "-m", str(self.cfg.models_dir / EMBED_MODEL), "--embeddings",
            "-ngl", "0", "-c", "2048", "-ub", "2048", "--port", str(EMBED_PORT), "--host", "127.0.0.1",
        ]  # fmt: skip

    def ensure(self) -> str | None:
        """The embeddings URL, starting the server when needed; None when it cannot run (no model file)."""
        if self._healthy():
            return EMBED_URL
        if not (self.cfg.models_dir / EMBED_MODEL).is_file():
            return None
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
        self._proc = self._spawn(
            self.command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags
        )
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                self._proc = None
                return None
            if self._healthy():
                return EMBED_URL
            time.sleep(self._poll)
        self.stop()
        return None

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
