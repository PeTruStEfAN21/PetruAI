"""Environment check: torch/CUDA/Unsloth versions and whether the base model loads in 4-bit on this GPU."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "infra" / "llama.cpp" / "models" / "hf" / "Qwen3.5-4B"


@dataclass
class EnvReport:
    torch_version: str
    cuda: bool
    bf16: bool
    unsloth_version: str
    model_loaded: bool
    peak_vram_gb: float
    error: str | None = None


def _versions() -> tuple[str, bool, bool, str]:
    import torch

    cuda = torch.cuda.is_available()
    bf16 = bool(cuda and torch.cuda.is_bf16_supported())
    try:
        import unsloth

        unsloth_version = getattr(unsloth, "__version__", "unknown")
    except Exception as exc:  # pragma: no cover - depends on the installed stack
        unsloth_version = f"import failed: {exc}"
    return torch.__version__, cuda, bf16, unsloth_version


def check_env(model_dir: Path, seq_len: int = 2048) -> EnvReport:
    torch_version, cuda, bf16, unsloth_version = _versions()
    report = EnvReport(torch_version, cuda, bf16, unsloth_version, model_loaded=False, peak_vram_gb=0.0)
    if not model_dir.is_dir():
        report.error = f"model dir not found: {model_dir}"
        return report
    if not cuda:
        report.error = "CUDA is not available"
        return report
    try:
        import torch
        from unsloth import FastLanguageModel

        torch.cuda.reset_peak_memory_stats()
        model, _tokenizer = FastLanguageModel.from_pretrained(
            str(model_dir), max_seq_length=seq_len, load_in_4bit=True, dtype=None
        )
        ids = torch.randint(0, 1000, (1, seq_len), device="cuda")
        with torch.no_grad():
            model(input_ids=ids)
        report.peak_vram_gb = round(torch.cuda.max_memory_allocated() / 1e9, 2)
        report.model_loaded = True
        del model
        torch.cuda.empty_cache()
    except Exception as exc:
        report.error = f"{type(exc).__name__}: {exc}"
    return report


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else MODEL_DIR
    print(json.dumps(asdict(check_env(target)), indent=2))
