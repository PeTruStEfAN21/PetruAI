import json
from pathlib import Path

import pytest

from petru_train import export as export_module
from petru_train.export import TUNED_FILE, convert_to_gguf, promote, quantize


def make_run(tmp_path: Path, passed: bool | None) -> Path:
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "candidate-Q4_K_M.gguf").write_bytes(b"new model")
    if passed is not None:
        (run_dir / "gate.json").write_text(json.dumps({"passed": passed, "reason": "x"}), encoding="utf-8")
    return run_dir


def test_promote_refuses_without_passed_gate(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    with pytest.raises(RuntimeError, match="gate"):
        promote(make_run(tmp_path, None), models)
    with pytest.raises(RuntimeError, match="gate"):
        promote(make_run(tmp_path / "b", False), models)
    assert not (models / TUNED_FILE).exists()


def test_promote_copies_and_rotates_the_previous_model(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / TUNED_FILE).write_bytes(b"old model")
    target = promote(make_run(tmp_path, True), models)
    assert target == models / TUNED_FILE and target.read_bytes() == b"new model"
    assert (models / "Qwen3.5-4B-petru.prev.gguf").read_bytes() == b"old model"
    assert TUNED_FILE == "Qwen3.5-4B-petru.gguf"


def capture(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append([str(c) for c in cmd])
        is_convert = "convert_hf_to_gguf.py" in str(cmd[1])
        out = (
            Path(cmd[cmd.index("--outfile") + 1]) if is_convert else Path(cmd[2])
        )  # quantize: exe in out qtype
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"gguf")

        class Done:
            returncode = 0
            stdout = stderr = ""

        return Done()

    monkeypatch.setattr(export_module.subprocess, "run", fake_run)
    return calls


def test_quantize_builds_the_llama_quantize_command(monkeypatch, tmp_path):
    calls = capture(monkeypatch)
    out = quantize(tmp_path / "cand-bf16.gguf", tmp_path / "cand-Q4_K_M.gguf")
    assert out == tmp_path / "cand-Q4_K_M.gguf" and out.exists()
    assert calls[0][0].endswith("llama-quantize.exe") and calls[0][-1] == "Q4_K_M"
    assert calls[0][1] == str(tmp_path / "cand-bf16.gguf") and calls[0][2] == str(out)


def test_convert_builds_the_converter_command(monkeypatch, tmp_path):
    calls = capture(monkeypatch)
    merged = tmp_path / "merged"
    merged.mkdir()
    out = convert_to_gguf(merged, tmp_path / "cand-bf16.gguf", python=Path("python.exe"))
    assert out.exists() and calls[0][0] == "python.exe" and calls[0][1].endswith("convert_hf_to_gguf.py")
    assert (
        calls[0][2] == str(merged)
        and "--outtype" in calls[0]
        and calls[0][calls[0].index("--outtype") + 1] == "bf16"
    )
