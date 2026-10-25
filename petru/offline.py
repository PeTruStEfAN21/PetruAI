"""Connectivity check and the offline package manifest."""

from __future__ import annotations

import socket
import tomllib
from collections.abc import Callable
from pathlib import Path

ECOSYSTEMS = ("python", "node", "flutter")
_PROBE = ("1.1.1.1", 53)
_online_cache: bool | None = None


def _tcp_connect(host: str, port: int, timeout: float) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        pass


def is_online(timeout_s: float = 1.0, connect: Callable[[str, int, float], None] | None = None) -> bool:
    """True when a TCP connection to a public resolver succeeds. The default probe is cached per process."""
    global _online_cache
    if connect is not None:
        try:
            connect(*_PROBE, timeout_s)
            return True
        except OSError:
            return False
    if _online_cache is None:
        try:
            _tcp_connect(*_PROBE, timeout_s)
            _online_cache = True
        except OSError:
            _online_cache = False
    return _online_cache


def load_offline_manifest(repo_root: Path) -> dict[str, list[str]]:
    """Packages cached for offline work, per ecosystem, from infra/offline/manifest.toml."""
    path = repo_root / "infra" / "offline" / "manifest.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    manifest: dict[str, list[str]] = {}
    for ecosystem in ECOSYSTEMS:
        table = data.get(ecosystem)
        if isinstance(table, dict) and table.get("packages"):
            manifest[ecosystem] = [str(p) for p in table["packages"]]
    return manifest
