"""Configuration: model tiers, llama-server location and user overrides."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

COMMON_SERVER_ARGS: list[str] = [
    "-ngl",
    "99",
    "--flash-attn",
    "on",
    "--cache-type-k",
    "q8_0",
    "--cache-type-v",
    "q8_0",
    "--jinja",
    "--cache-ram",  # the host prompt cache: 8 GB by default per server, too much for two next to the 35B
    "1024",
]


@dataclass
class Tier:
    name: str
    model_file: str
    ctx: int
    extra_args: list[str] = field(default_factory=list)
    max_iterations: int = 60  # tool calls per turn; the limit costs time, not memory


@dataclass
class Config:
    repo_root: Path
    models_dir: Path
    server_exe: Path
    port: int = 8080
    tiers: dict[str, Tier] = field(default_factory=dict)
    default_tier: str = "default"


def default_tiers() -> dict[str, Tier]:
    return {
        "default": Tier("default", "Qwen3.5-9B.IQ4_XS.gguf", ctx=16384),
        "quality": Tier(
            "quality",
            "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf",
            ctx=32768,
            extra_args=["--cpu-moe"],
            max_iterations=100,
        ),
        "fast": Tier("fast", "Qwen3.5-4B.IQ4_XS.gguf", ctx=32768),
    }


TUNED_FILE = "Qwen3.5-4B-petru.gguf"  # written by training/petru_train/export.py when the gate passes


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` to the directory holding infra/llama.cpp or the petru pyproject."""
    for candidate in [start.resolve(), *start.resolve().parents]:
        if (candidate / "infra" / "llama.cpp").is_dir():
            return candidate
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and 'name = "petru"' in pyproject.read_text(encoding="utf-8"):
            return candidate
    return Path(__file__).resolve().parent.parent


def _user_config() -> dict:
    path = Path.home() / ".petru" / "config.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_config(repo_root: Path | None = None) -> Config:
    root = repo_root or find_repo_root(Path(__file__).resolve().parent)
    cfg = Config(
        repo_root=root,
        models_dir=root / "infra" / "llama.cpp" / "models",
        server_exe=root / "infra" / "llama.cpp" / "bin" / "llama-server.exe",
        tiers=default_tiers(),
    )
    if (cfg.models_dir / TUNED_FILE).is_file():  # a promoted fine-tune (training pipeline)
        cfg.tiers["tuned"] = Tier("tuned", TUNED_FILE, ctx=32768)
    for gguf in sorted((cfg.models_dir / "specialists").glob("*.gguf")):  # promoted language specialists
        cfg.tiers[f"tuned-{gguf.stem}"] = Tier(f"tuned-{gguf.stem}", f"specialists/{gguf.name}", ctx=32768)
    user = _user_config()
    server = user.get("server", {})
    if "port" in server:
        cfg.port = int(server["port"])
    if "default_tier" in server:
        cfg.default_tier = str(server["default_tier"])
    for name, overrides in user.get("tiers", {}).items():
        base = cfg.tiers.get(name) or Tier(name, model_file="", ctx=8192)
        allowed = {k: v for k, v in overrides.items() if k in ("model_file", "ctx", "extra_args")}
        cfg.tiers[name] = replace(base, **allowed)
    return cfg
