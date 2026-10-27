"""Build train/eval JSONL from the catalogs: mine commits (cached per repo), filter, dedup, balance, split."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from petru_train.commits import commit_to_sample, iter_commits
from petru_train.dedup import balance_by_language, minhash_dedup
from petru_train.samples import Sample, load_tools, read_jsonl, split, write_jsonl

TRAINING_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = TRAINING_DIR / "config" / "dataset.toml"
CACHE_VERSION = 5  # bump when the mining filters or language labels change, so every repo is mined again


def cache_dir(out_dir: Path) -> Path:
    return out_dir / f"cache-v{CACHE_VERSION}"


@dataclass
class DatasetConfig:
    local_repos: Path
    github_repos: Path | None
    out_dir: Path
    max_commits_per_repo: int = 300
    eval_frac: float = 0.05
    max_share: float = 0.4
    extra_jsonl: list[Path] = field(default_factory=list)
    commit_ratio: float | None = None  # mined commits kept per verified trajectory; None = all of them


def load_dataset_config(path: Path = DEFAULT_CONFIG, base_dir: Path | None = None) -> DatasetConfig:
    base = base_dir or path.parent.parent
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    def resolve(value: str | None) -> Path | None:
        return None if value is None else (base / value)

    return DatasetConfig(
        local_repos=resolve(data["local_repos"]),
        github_repos=resolve(data.get("github_repos")),
        out_dir=resolve(data.get("out_dir", "data")),
        max_commits_per_repo=int(data.get("max_commits_per_repo", 300)),
        eval_frac=float(data.get("eval_frac", 0.05)),
        max_share=float(data.get("max_share", 0.4)),
        extra_jsonl=[base / p for p in data.get("extra_jsonl", [])],
        commit_ratio=float(data["commit_ratio"]) if "commit_ratio" in data else None,
    )


@dataclass
class RepoEntry:
    name: str
    path: Path
    license: str


def _read_catalog(path: Path | None, default_license: str, raw_root: Path | None = None) -> list[RepoEntry]:
    if path is None or not path.is_file():
        return []
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    entries = []
    for item in data.get("repo", []):
        if "path" in item:
            repo_path, name = Path(item["path"]), item.get("name") or Path(item["path"]).name
        else:  # github catalog: url -> corpus/raw/<owner>__<repo>
            owner_repo = item["url"].rstrip("/").removesuffix(".git").split("/")[-2:]
            name = "__".join(owner_repo)
            repo_path = (raw_root or path.parent / "raw") / name
        entries.append(RepoEntry(name, repo_path, str(item.get("license") or default_license)))
    return entries


def _cache_is_fresh(cache: Path, repo: Path) -> bool:
    head = repo / ".git" / "HEAD"
    return cache.is_file() and head.is_file() and cache.stat().st_mtime >= head.stat().st_mtime


def _mine(entry: RepoEntry, cfg: DatasetConfig, tools: list[dict]) -> list[Sample]:
    cache = cache_dir(cfg.out_dir) / f"{entry.name}.jsonl"
    if _cache_is_fresh(cache, entry.path):
        return read_jsonl(cache)
    samples = [
        commit_to_sample(commit, entry.name, entry.license, tools)
        for commit in iter_commits(entry.path, max_commits=cfg.max_commits_per_repo)
    ]
    write_jsonl(cache, samples)
    return samples


def cap_commits(commits: list[Sample], trajectories: int, ratio: float | None) -> list[Sample]:
    """At most `ratio` mined commits per verified trajectory, a stable pseudo-random choice. A replayed commit
    shows edits with no plan, no test run and no reasoning: in bulk it teaches the agent to skip all three."""
    if ratio is None:
        return commits
    keep = int(trajectories * ratio)
    return sorted(commits, key=lambda s: hashlib.sha1(s.id.encode("utf-8")).hexdigest())[:keep]


def build(cfg: DatasetConfig) -> dict:
    tools = load_tools()
    entries = _read_catalog(cfg.local_repos, "local") + _read_catalog(cfg.github_repos, "unknown")
    samples: list[Sample] = []
    sources: Counter[str] = Counter()
    for entry in entries:
        if not (entry.path / ".git").exists():
            print(f"skipping {entry.name}: no git repository at {entry.path}")
            continue
        mined = _mine(entry, cfg, tools)
        for sample in mined:  # the cache may predate a tool change; train on the schemas the agent uses now
            sample.tools = tools
        samples.extend(mined)
    extras: list[Sample] = []
    for extra in cfg.extra_jsonl:
        if extra.is_file():
            extras.extend(read_jsonl(extra))
    samples = cap_commits(samples, len(extras), cfg.commit_ratio) + extras
    sources["commit"], sources["extra"] = len(samples) - len(extras), len(extras)
    deduped = minhash_dedup(samples)
    balanced = balance_by_language(deduped, max_share=cfg.max_share)
    train, eval_ = split(balanced, eval_frac=cfg.eval_frac)
    write_jsonl(cfg.out_dir / "train.jsonl", train)
    write_jsonl(cfg.out_dir / "eval.jsonl", eval_)
    stats = {
        "repos": [e.name for e in entries],
        "sources": dict(sources),
        "languages": dict(Counter(s.language for s in balanced)),
        "dedup_removed": len(samples) - len(deduped),
        "balance_removed": len(deduped) - len(balanced),
        "train": len(train),
        "eval": len(eval_),
    }
    (cfg.out_dir / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the PetruAI SFT dataset.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    stats = build(load_dataset_config(args.config))
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
