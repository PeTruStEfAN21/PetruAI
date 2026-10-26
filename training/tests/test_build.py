import json
from pathlib import Path

import pytest

from petru_train import build as build_module
from petru_train.build import DatasetConfig, build, cache_dir, load_dataset_config
from petru_train.samples import read_jsonl, write_jsonl
from tests.test_commits import commit_file, git
from tests.test_dedup import sample_with_content


def tiny_repo(root: Path, name: str, n: int) -> Path:
    repo = root / name
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "user.email", "t@t")
    for i in range(n):
        content = f"{name} value = {i}\n" * (i + 1)  # distinct per repo, so dedup keeps every commit
        commit_file(repo, f"mod{i}.py", content, f"Add module number {i} with values")
    return repo


def catalog(path: Path, repos: list[Path]) -> Path:
    lines = []
    for repo in repos:
        lines += ["[[repo]]", f'name = "{repo.name}"', f'path = "{repo.as_posix()}"', ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_load_dataset_config_resolves_paths_relative_to_training_dir(tmp_path):
    cfg_file = tmp_path / "dataset.toml"
    cfg_file.write_text(
        'local_repos = "corpus/local_repos.toml"\nout_dir = "data"\nmax_commits_per_repo = 50\n',
        encoding="utf-8",
    )
    cfg = load_dataset_config(cfg_file, base_dir=tmp_path)
    assert cfg.local_repos == tmp_path / "corpus" / "local_repos.toml"
    assert cfg.out_dir == tmp_path / "data" and cfg.github_repos is None
    assert cfg.max_commits_per_repo == 50 and cfg.eval_frac == 0.05 and cfg.max_share == 0.4


def test_build_writes_split_cache_and_stats(tmp_path):
    repos = [tiny_repo(tmp_path, "alpha", 25), tiny_repo(tmp_path, "beta", 5)]
    cfg = DatasetConfig(
        local_repos=catalog(tmp_path / "local.toml", repos), github_repos=None, out_dir=tmp_path / "out"
    )
    stats = build(cfg)
    train = read_jsonl(cfg.out_dir / "train.jsonl")
    eval_ = read_jsonl(cfg.out_dir / "eval.jsonl")
    assert len(train) + len(eval_) == 30 and len(eval_) >= 1
    assert (cache_dir(cfg.out_dir) / "alpha.jsonl").exists() and (
        cache_dir(cfg.out_dir) / "beta.jsonl"
    ).exists()
    saved = json.loads((cfg.out_dir / "stats.json").read_text(encoding="utf-8"))
    assert saved == stats
    assert stats["sources"]["commit"] == 30 and stats["languages"]["python"] == 30
    assert stats["train"] == len(train) and stats["eval"] == len(eval_)
    assert all(s.license == "local" and s.repo in ("alpha", "beta") for s in train + eval_)


def test_build_reuses_cache_and_includes_extra_jsonl(tmp_path, monkeypatch):
    repos = [tiny_repo(tmp_path, "alpha", 3)]
    cfg = DatasetConfig(
        local_repos=catalog(tmp_path / "local.toml", repos), github_repos=None, out_dir=tmp_path / "out"
    )
    build(cfg)

    def boom(*args, **kwargs):
        raise AssertionError("iter_commits must not run when the cache is fresh")

    monkeypatch.setattr(build_module, "iter_commits", boom)
    extra = tmp_path / "extra.jsonl"
    write_jsonl(extra, [sample_with_content("t1", "trajectory content", "dart")])
    cfg.extra_jsonl = [extra]
    stats = build(cfg)
    assert stats["sources"] == {"commit": 3, "extra": 1}
    all_ids = {s.id for s in read_jsonl(cfg.out_dir / "train.jsonl") + read_jsonl(cfg.out_dir / "eval.jsonl")}
    assert "t1" in all_ids


def test_build_refreshes_tool_schemas_of_cached_commit_samples(tmp_path, monkeypatch):
    repos = [tiny_repo(tmp_path, "alpha", 3)]
    cfg = DatasetConfig(
        local_repos=catalog(tmp_path / "local.toml", repos), github_repos=None, out_dir=tmp_path / "out"
    )
    monkeypatch.setattr(build_module, "load_tools", lambda: [{"old": True}])
    build(cfg)
    monkeypatch.setattr(build_module, "load_tools", lambda: [{"new": True}])
    build(cfg)  # served from the cache, which still holds the old schemas
    samples = read_jsonl(cfg.out_dir / "train.jsonl") + read_jsonl(cfg.out_dir / "eval.jsonl")
    assert samples and all(s.tools == [{"new": True}] for s in samples)


def test_build_skips_missing_repo_with_a_warning(tmp_path, capsys):
    cfg = DatasetConfig(
        local_repos=catalog(tmp_path / "local.toml", [tmp_path / "ghost"]),
        github_repos=None,
        out_dir=tmp_path / "out",
    )
    stats = build(cfg)
    assert stats["train"] == 0 and "ghost" in capsys.readouterr().out


@pytest.mark.parametrize("field", ["train", "eval", "dedup_removed", "balance_removed"])
def test_stats_have_expected_fields(tmp_path, field):
    cfg = DatasetConfig(
        local_repos=catalog(tmp_path / "l.toml", []), github_repos=None, out_dir=tmp_path / "o"
    )
    assert field in build(cfg)
