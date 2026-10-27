"""Start llama-server for a candidate GGUF on a side port, for evaluation only."""

from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_EXE = REPO_ROOT / "infra" / "llama.cpp" / "bin" / "llama-server.exe"
COMMON_ARGS = [
    "-ngl",
    "99",
    "--flash-attn",
    "on",
    "--cache-type-k",
    "q8_0",
    "--cache-type-v",
    "q8_0",
    "--jinja",
]


def server_command(gguf: Path, port: int = 8081, ctx: int = 16384, extra: tuple[str, ...] = ()) -> list[str]:
    return [
        str(SERVER_EXE), "-m", gguf.as_posix(), "-c", str(ctx), *COMMON_ARGS,
        "--port", str(port), "--host", "127.0.0.1", *extra,
    ]  # fmt: skip


def is_healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_server(
    gguf: Path, port: int = 8081, ctx: int = 16384, log: Path | None = None, extra: tuple[str, ...] = ()
) -> subprocess.Popen:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
    stderr = open(log, "ab") if log else subprocess.DEVNULL  # noqa: SIM115 - closed with the process
    return subprocess.Popen(
        server_command(gguf, port, ctx, extra), stdout=subprocess.DEVNULL, stderr=stderr, creationflags=flags
    )


def wait_healthy(port: int, timeout_s: float = 180.0, proc: subprocess.Popen | None = None) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        if is_healthy(port):
            return True
        time.sleep(0.5)
    return False


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
