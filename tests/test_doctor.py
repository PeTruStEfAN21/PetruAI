from pathlib import Path

from petru import cli, doctor
from petru.config import Config, default_tiers
from petru.doctor import Check, Probe, render, run_doctor


def make_cfg(tmp_path: Path, models=("Qwen3.5-9B.IQ4_XS.gguf", "Qwen3.5-4B.IQ4_XS.gguf")) -> Config:
    root = tmp_path / "repo"
    models_dir = root / "infra" / "llama.cpp" / "models"
    models_dir.mkdir(parents=True)
    for name in models:
        (models_dir / name).write_bytes(b"x" * 1024)
    exe = root / "infra" / "llama.cpp" / "bin" / "llama-server.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"exe")
    return Config(root, models_dir, exe, tiers=default_tiers())


def healthy_probe(tmp_path: Path) -> Probe:
    home = tmp_path / "home"
    (home / "docs_index.sqlite").parent.mkdir(parents=True)
    (home / "docs_index.sqlite").write_bytes(b"x")
    libs = tmp_path / "local" / "tree-sitter-language-pack" / "v1.22.1" / "libs"
    libs.mkdir(parents=True)
    (libs / "tree_sitter_python.dll").write_bytes(b"x")
    (tmp_path / "local" / "npm-cache" / "_cacache").mkdir(parents=True)
    (tmp_path / "local" / "Pub" / "Cache").mkdir(parents=True)
    return Probe(
        which=lambda name: f"C:/bin/{name}.exe",
        run=lambda cmd: (0, "NVIDIA GeForce RTX 4050 Laptop GPU, 6141" if cmd[0] == "nvidia-smi" else "ok"),
        home=home,
        local_appdata=tmp_path / "local",
        free_gb=lambda path: 100.0,
        online=lambda: False,
    )


def by_name(checks: list[Check]) -> dict[str, Check]:
    return {c.name: c for c in checks}


def test_healthy_machine_has_no_failures(tmp_path):
    cfg = make_cfg(tmp_path)
    wheels = cfg.repo_root / "infra" / "offline" / "wheels" / "py314"
    wheels.mkdir(parents=True)
    (wheels / "pytest-9.whl").write_bytes(b"w")
    checks = by_name(run_doctor(cfg, healthy_probe(tmp_path)))
    assert not [c for c in checks.values() if c.status == "fail"]
    assert (
        checks["GPU"].status == "ok"
        and "RTX 4050" in checks["GPU"].detail
        and "6.0 GB" in checks["GPU"].detail
    )
    assert checks["model default"].status == "ok" and checks["model quality"].status == "warn"
    assert checks["connectivity"].detail == "offline"


def test_missing_default_model_and_server_fail_with_a_fix(tmp_path):
    cfg = make_cfg(tmp_path, models=())
    cfg.server_exe.unlink()
    checks = by_name(run_doctor(cfg, healthy_probe(tmp_path)))
    assert checks["model default"].status == "fail" and "setup-models.ps1" in checks["model default"].fix
    assert checks["llama-server"].status == "fail" and "setup.ps1" in checks["llama-server"].fix


def test_missing_git_fails_and_missing_flutter_warns(tmp_path):
    probe = healthy_probe(tmp_path)
    probe.which = lambda name: None if name in ("git", "flutter") else f"C:/bin/{name}.exe"
    checks = by_name(run_doctor(make_cfg(tmp_path), probe))
    assert checks["git"].status == "fail" and checks["flutter"].status == "warn"


def test_uv_found_through_the_py_launcher(tmp_path):
    probe = healthy_probe(tmp_path)
    probe.which = lambda name: None if name == "uv" else f"C:/bin/{name}.exe"
    probe.run = lambda cmd: (0, "uv 0.13.5") if cmd[:3] == ["py", "-3.14", "-m"] else (1, "")
    assert by_name(run_doctor(make_cfg(tmp_path), probe))["uv"].status == "ok"


def test_no_gpu_fails_and_low_disk_warns(tmp_path):
    probe = healthy_probe(tmp_path)
    probe.run = lambda cmd: (1, "") if cmd[0] == "nvidia-smi" else (0, "ok")
    probe.free_gb = lambda path: 5.0
    checks = by_name(run_doctor(make_cfg(tmp_path), probe))
    assert checks["GPU"].status == "fail" and checks["disk"].status == "warn"


def test_offline_readiness_warnings(tmp_path):
    probe = healthy_probe(tmp_path)
    probe.local_appdata = tmp_path / "empty"
    probe.home = tmp_path / "empty-home"
    checks = by_name(run_doctor(make_cfg(tmp_path), probe))
    for name in ("npm cache", "pub cache", "python wheelhouse", "tree-sitter grammars", "docs index"):
        assert checks[name].status == "warn", name


def test_render_and_exit_code(tmp_path, monkeypatch, capsys):
    text = render([Check("a", "ok", "fine"), Check("b", "fail", "broken", "do x")])
    assert "FAIL" in text and "do x" in text
    monkeypatch.setattr(doctor, "run_doctor", lambda cfg, probe=None: [Check("b", "fail", "broken", "do x")])
    assert cli.run_subcommand(["doctor"]) == 1
    monkeypatch.setattr(doctor, "run_doctor", lambda cfg, probe=None: [Check("a", "ok", "fine")])
    assert cli.run_subcommand(["doctor"]) == 0
    assert "a" in capsys.readouterr().out
