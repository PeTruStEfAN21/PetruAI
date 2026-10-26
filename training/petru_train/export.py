"""Adapter merge, GGUF conversion, quantization and the gated promotion to the `tuned` tier."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

TRAINING_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TRAINING_DIR.parent
CONVERT_SCRIPT = REPO_ROOT / "infra" / "llama.cpp" / "convert" / "convert_hf_to_gguf.py"
QUANTIZE_EXE = REPO_ROOT / "infra" / "llama.cpp" / "bin" / "llama-quantize.exe"
MODELS_DIR = REPO_ROOT / "infra" / "llama.cpp" / "models"
TUNED_FILE = "Qwen3.5-4B-petru.gguf"  # must match petru.config.TUNED_FILE
PREV_FILE = "Qwen3.5-4B-petru.prev.gguf"


def merge_adapter(base_model: Path, adapter_dir: Path, out_dir: Path) -> Path:
    """Merge the LoRA into bf16 weights on the CPU (32 GB RAM) and save them with the tokenizer.
    Runs in a child process so the ~9 GB of weights leave RAM when it is done."""
    from petru_train.isolate import run_isolated

    run_isolated(
        "petru_train.export:merge_from_json",
        {"base_model": str(base_model), "adapter_dir": str(adapter_dir), "out_dir": str(out_dir)},
    )
    return out_dir


def merge_from_json(base_model: str, adapter_dir: str, out_dir: str) -> str:
    return str(_merge_in_process(Path(base_model), Path(adapter_dir), Path(out_dir)))


def _merge_in_process(base_model: Path, adapter_dir: Path, out_dir: Path) -> Path:
    import torch
    from peft import PeftModel
    from transformers import AutoProcessor, AutoTokenizer

    try:
        from transformers import AutoModelForImageTextToText as AutoModel
    except ImportError:  # pragma: no cover
        from transformers import AutoModelForCausalLM as AutoModel

    model = AutoModel.from_pretrained(str(base_model), dtype=torch.bfloat16, device_map="cpu")
    merged = PeftModel.from_pretrained(model, str(adapter_dir)).merge_and_unload()
    out_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(out_dir), safe_serialization=True)
    AutoTokenizer.from_pretrained(str(base_model)).save_pretrained(str(out_dir))
    try:
        AutoProcessor.from_pretrained(str(base_model)).save_pretrained(str(out_dir))
    except Exception:  # text-only checkpoints have no processor
        pass
    for name in ("chat_template.jinja",):
        if (base_model / name).is_file() and not (out_dir / name).exists():
            shutil.copy2(base_model / name, out_dir / name)
    return out_dir


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({proc.returncode}):\n{(proc.stderr or proc.stdout)[-3000:]}")


def convert_to_gguf(merged_dir: Path, out_file: Path, python: Path = Path(sys.executable)) -> Path:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    _run([str(python), str(CONVERT_SCRIPT), str(merged_dir), "--outfile", str(out_file), "--outtype", "bf16"])
    if not out_file.exists():
        raise RuntimeError(f"conversion produced no file at {out_file}")
    return out_file


def quantize(gguf_bf16: Path, out_file: Path, qtype: str = "Q4_K_M") -> Path:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    _run([str(QUANTIZE_EXE), str(gguf_bf16), str(out_file), qtype])
    if not out_file.exists():
        raise RuntimeError(f"quantization produced no file at {out_file}")
    return out_file


def candidate_file(run_dir: Path) -> Path | None:
    files = sorted(run_dir.glob("candidate-Q*.gguf"))
    return files[0] if files else None


def promote(run_dir: Path, models_dir: Path = MODELS_DIR) -> Path:
    """Copy the run's quantized candidate to the models folder as the `tuned` tier. Needs a passed gate."""
    gate_file = run_dir / "gate.json"
    if not gate_file.is_file():
        raise RuntimeError(f"no gate.json in {run_dir}: run the evaluation first (gate not passed)")
    gate = json.loads(gate_file.read_text(encoding="utf-8"))
    if not gate.get("passed"):
        raise RuntimeError(f"gate not passed for {run_dir}: {gate.get('reason')}")
    candidate = candidate_file(run_dir)
    if candidate is None:
        raise RuntimeError(f"no quantized candidate in {run_dir}")
    target = models_dir / TUNED_FILE
    if target.exists():
        shutil.copy2(target, models_dir / PREV_FILE)
    shutil.copy2(candidate, target)
    return target


def export_run(run_dir: Path, base_model: Path, qtype: str = "Q4_K_M") -> Path:
    merged = merge_adapter(base_model, run_dir / "adapter", run_dir / "merged")
    bf16 = convert_to_gguf(merged, run_dir / "candidate-bf16.gguf")
    quantized = quantize(bf16, run_dir / f"candidate-{qtype}.gguf", qtype)
    bf16.unlink(missing_ok=True)  # 8 GB we do not need once quantized
    shutil.rmtree(merged, ignore_errors=True)
    return quantized


def main(argv: list[str] | None = None) -> int:
    from petru_train.env import MODEL_DIR

    parser = argparse.ArgumentParser(description="Merge, convert, quantize and optionally promote a run.")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--qtype", default="Q4_K_M")
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--base-model", type=Path, default=MODEL_DIR)
    args = parser.parse_args(argv)
    quantized = export_run(args.run, args.base_model, args.qtype)
    print(f"candidate: {quantized} ({quantized.stat().st_size / 1e9:.2f} GB)")
    if args.promote:
        print(f"promoted to {promote(args.run)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
