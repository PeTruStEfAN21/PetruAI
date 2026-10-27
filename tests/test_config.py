from pathlib import Path

from petru.config import find_repo_root, load_config


def test_default_tiers_match_spec(tmp_path):
    cfg = load_config(repo_root=tmp_path)
    assert cfg.tiers["default"].model_file == "Qwen3.5-9B.IQ4_XS.gguf"
    assert cfg.tiers["default"].ctx == 16384
    assert cfg.tiers["quality"].model_file == "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"
    assert "--cpu-moe" in cfg.tiers["quality"].extra_args
    assert cfg.tiers["fast"].model_file == "Qwen3.5-4B.IQ4_XS.gguf"
    assert cfg.port == 8080
    assert cfg.default_tier == "default"
    assert cfg.models_dir == tmp_path / "infra" / "llama.cpp" / "models"
    assert cfg.server_exe == tmp_path / "infra" / "llama.cpp" / "bin" / "llama-server.exe"


def test_user_config_overrides_port_and_ctx(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".petru").mkdir(parents=True)
    (home / ".petru" / "config.toml").write_text(
        "[server]\nport = 9090\n[tiers.default]\nctx = 12288\n", encoding="utf-8"
    )
    monkeypatch.setattr(Path, "home", lambda: home)
    cfg = load_config(repo_root=tmp_path)
    assert cfg.port == 9090
    assert cfg.tiers["default"].ctx == 12288
    assert cfg.tiers["default"].model_file == "Qwen3.5-9B.IQ4_XS.gguf"


def test_find_repo_root_walks_up(tmp_path):
    (tmp_path / "infra" / "llama.cpp").mkdir(parents=True)
    start = tmp_path / "a" / "b"
    start.mkdir(parents=True)
    assert find_repo_root(start) == tmp_path


def test_the_quality_tier_may_work_longer_per_turn():
    from petru.config import default_tiers

    tiers = default_tiers()
    assert tiers["quality"].max_iterations > tiers["default"].max_iterations >= 40
