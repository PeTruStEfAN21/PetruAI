"""`petru doctor`: what is ready, what is missing, and the exact fix, offline readiness included."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from petru.config import Config

Status = Literal["ok", "warn", "fail"]
SETUP = "powershell -ExecutionPolicy Bypass -File infra/setup.ps1"
EMBED_MODEL = "embeddinggemma-2-Q8_0.gguf"
MODEL_FLAGS = {"default": "-IncludeMedium", "quality": "-IncludeAll", "fast": ""}  # setup-models.ps1 switches


@dataclass
class Check:
    name: str
    status: Status
    detail: str
    fix: str = ""


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def _free_gb(path: Path) -> float:
    target = path if path.exists() else path.anchor or "."
    return shutil.disk_usage(target).free / 1e9


def _online() -> bool:
    from petru.offline import is_online

    return is_online()


@dataclass
class Probe:
    """Everything the checks look at outside Python, injectable for tests."""

    which: Callable[[str], str | None] = shutil.which
    run: Callable[[list[str]], tuple[int, str]] = _run
    home: Path = field(default_factory=lambda: Path(os.environ.get("PETRU_HOME") or Path.home() / ".petru"))
    local_appdata: Path = field(default_factory=lambda: Path(os.environ.get("LOCALAPPDATA", Path.home())))
    free_gb: Callable[[Path], float] = _free_gb
    online: Callable[[], bool] = _online


def _python(probe: Probe) -> list[Check]:
    version = sys.version.split()[0]
    status: Status = "ok" if sys.version_info >= (3, 14) else "warn"
    checks = [
        Check(
            "python",
            status,
            version,
            "" if status == "ok" else "install Python 3.14 (winget install Python.Python.3.14)",
        )
    ]
    has_uv = probe.which("uv") is not None or any(
        probe.run(cmd)[0] == 0
        for cmd in ([sys.executable, "-m", "uv", "--version"], ["py", "-3.14", "-m", "uv", "--version"])
    )
    checks.append(
        Check(
            "uv", "ok" if has_uv else "warn", "found" if has_uv else "missing", "py -3.14 -m pip install uv"
        )
    )
    return checks


def _server(cfg: Config) -> Check:
    if cfg.server_exe.is_file():
        return Check("llama-server", "ok", str(cfg.server_exe))
    return Check("llama-server", "fail", f"missing: {cfg.server_exe}", SETUP)


def _gpu(probe: Probe) -> Check:
    code, out = probe.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    if code != 0 or not out:
        return Check("GPU", "fail", "no NVIDIA GPU found (nvidia-smi failed)", "install the NVIDIA driver")
    name, _, mib = out.splitlines()[0].rpartition(",")
    try:
        vram = float(mib) / 1024
    except ValueError:
        return Check("GPU", "warn", out.splitlines()[0])
    status: Status = "ok" if vram >= 5.5 else "warn"
    return Check(
        "GPU", status, f"{name.strip()}, {vram:.1f} GB VRAM", "" if status == "ok" else "use --model fast"
    )


def _models(cfg: Config) -> list[Check]:
    checks = []
    for name, tier in cfg.tiers.items():
        path = cfg.models_dir / tier.model_file
        if path.is_file():
            checks.append(
                Check(f"model {name}", "ok", f"{tier.model_file} ({path.stat().st_size / 1e9:.1f} GB)")
            )
        else:
            status: Status = "fail" if name == cfg.default_tier else "warn"
            checks.append(
                Check(
                    f"model {name}",
                    status,
                    f"missing {tier.model_file}",
                    f"powershell -File infra/setup-models.ps1 {MODEL_FLAGS.get(name, '-IncludeMedium')}",
                )
            )
    embed = cfg.models_dir / EMBED_MODEL
    checks.append(
        Check("model embeddings", "ok", EMBED_MODEL)
        if embed.is_file()
        else Check(
            "model embeddings",
            "warn",
            "missing: code search uses keywords only",
            "powershell -File infra/setup-models.ps1",
        )
    )
    return checks


def _tools(probe: Probe) -> list[Check]:
    checks = []
    for tool, required in (
        ("git", True),
        ("node", False),
        ("npm", False),
        ("flutter", False),
        ("dart", False),
    ):
        found = probe.which(tool)
        if found:
            checks.append(Check(tool, "ok", found))
        else:
            status: Status = "fail" if required else "warn"
            checks.append(
                Check(
                    tool,
                    status,
                    "not on PATH",
                    f"install {tool}" + ("" if required else " for those projects"),
                )
            )
    return checks


def _offline(cfg: Config, probe: Probe) -> list[Check]:
    wheels = cfg.repo_root / "infra" / "offline" / "wheels"
    count = len(list(wheels.glob("py3*/*.whl"))) if wheels.is_dir() else 0
    npm = probe.local_appdata / "npm-cache" / "_cacache"
    pub = probe.local_appdata / "Pub" / "Cache"
    grammars = list((probe.local_appdata / "tree-sitter-language-pack").glob("*/libs/*"))
    docs = probe.home / "docs_index.sqlite"
    build_caches = "powershell -File infra/offline/build_caches.ps1"
    return [
        Check("python wheelhouse", "ok" if count else "warn", f"{count} wheels", build_caches),
        Check("npm cache", "ok" if npm.is_dir() else "warn", str(npm), build_caches),
        Check("pub cache", "ok" if pub.is_dir() else "warn", str(pub), build_caches),
        Check(
            "tree-sitter grammars",
            "ok" if grammars else "warn",
            f"{len(grammars)} cached",
            "run `petru index --no-embed` once while online",
        ),  # fmt: skip
        Check("docs index", "ok" if docs.is_file() else "warn", str(docs), "petru index --docs --no-embed"),
    ]


def _disk(cfg: Config, probe: Probe) -> Check:
    free = probe.free_gb(cfg.repo_root)
    return Check(
        "disk", "ok" if free >= 20 else "warn", f"{free:.0f} GB free", "free space for models and caches"
    )


def _training(cfg: Config) -> Check:
    venv = cfg.repo_root / "training" / ".venv"
    if venv.is_dir():
        return Check("training env", "ok", str(venv))
    return Check(
        "training env",
        "warn",
        "not created (only needed for fine-tuning)",
        "cd training; py -3.14 -m uv sync",
    )


def run_doctor(cfg: Config, probe: Probe | None = None) -> list[Check]:
    probe = probe or Probe()
    checks = [*_python(probe), _server(cfg), _gpu(probe), *_models(cfg), *_tools(probe)]
    checks += [*_offline(cfg, probe), _disk(cfg, probe), _training(cfg)]
    checks.append(Check("connectivity", "ok", "online" if probe.online() else "offline"))
    return checks


def render(checks: list[Check]) -> str:
    marks = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}
    width = max((len(c.name) for c in checks), default=4)
    lines = []
    for check in checks:
        line = f"{marks[check.status]}  {check.name.ljust(width)}  {check.detail}"
        if check.status != "ok" and check.fix:
            line += f"\n      {' ' * width}  fix: {check.fix}"
        lines.append(line)
    failed = sum(c.status == "fail" for c in checks)
    warned = sum(c.status == "warn" for c in checks)
    lines.append(f"\n{failed} failed, {warned} warnings, {len(checks) - failed - warned} ok")
    return "\n".join(lines)
