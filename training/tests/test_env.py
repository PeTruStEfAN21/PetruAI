import pytest

from petru_train.env import MODEL_DIR, check_env


def test_env_report_without_model_dir(tmp_path):
    report = check_env(tmp_path / "missing")
    assert report.model_loaded is False
    assert "not found" in (report.error or "")
    assert isinstance(report.cuda, bool) and report.torch_version


@pytest.mark.gpu
def test_base_model_loads_in_4bit_under_6gb():
    assert MODEL_DIR.is_dir(), f"base weights missing at {MODEL_DIR}"
    report = check_env(MODEL_DIR, seq_len=2048)
    assert report.cuda and report.model_loaded, report.error
    assert report.peak_vram_gb < 5.5
