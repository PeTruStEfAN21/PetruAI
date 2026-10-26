from petru import cli, config
from petru.config import TUNED_FILE, load_config


def test_tuned_tier_appears_only_when_the_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_user_config", lambda: {})
    models = tmp_path / "infra" / "llama.cpp" / "models"
    models.mkdir(parents=True)
    assert "tuned" not in load_config(tmp_path).tiers
    (models / TUNED_FILE).write_bytes(b"gguf")
    tier = load_config(tmp_path).tiers["tuned"]
    assert tier.model_file == TUNED_FILE == "Qwen3.5-4B-petru.gguf" and tier.ctx == 32768


def test_cli_accepts_the_tuned_tier():
    assert cli.build_parser().parse_args(["--model", "tuned"]).model == "tuned"
