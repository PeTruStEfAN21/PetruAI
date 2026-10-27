"""Language specialists: which samples each one learns from, and the data files it trains on."""

from __future__ import annotations

import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from petru_train.samples import Sample, read_jsonl, write_jsonl

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "specialists.toml"
# Documentation and configuration: they belong to whichever ecosystem their repository is written in.
AGNOSTIC = frozenset({"markdown", "yaml", "json", "toml", "unknown"})


@dataclass
class Specialist:
    name: str
    languages: list[str]
    tasks: list[str]  # prefixes of the harness tasks that evaluate it (training/tasks/<prefix>_*.toml)
    epochs: float = 2.0
    repos: list[str] = field(
        default_factory=list
    )  # optional: only these repositories (e.g. Python web vs data)


def load_specialists(path: Path = DEFAULT_CONFIG) -> list[Specialist]:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return [
        Specialist(
            name=str(entry["name"]),
            languages=[str(x) for x in entry["languages"]],
            tasks=[str(x) for x in entry.get("tasks", [])],
            epochs=float(entry.get("epochs", Specialist.epochs)),
            repos=[str(x) for x in entry.get("repos", [])],
        )
        for entry in data.get("specialist", [])
    ]


def repo_ecosystems(samples: list[Sample]) -> dict[str, str]:
    """Each repository's dominant code language; repositories with only docs and configuration have none."""
    counts: dict[str, Counter] = {}
    for sample in samples:
        if sample.language not in AGNOSTIC:
            counts.setdefault(sample.repo, Counter())[sample.language] += 1
    return {repo: counter.most_common(1)[0][0] for repo, counter in counts.items()}


def select_samples(samples: list[Sample], specialist: Specialist, ecosystems: dict[str, str]) -> list[Sample]:
    """The specialist's languages, plus the docs and configuration of repositories written in them."""
    chosen = []
    for sample in samples:
        if specialist.repos and sample.repo not in specialist.repos:
            continue
        own = sample.language in specialist.languages
        ecosystem_docs = sample.language in AGNOSTIC and ecosystems.get(sample.repo) in specialist.languages
        if own or ecosystem_docs:
            chosen.append(sample)
    return chosen


def write_specialist_data(train_file: Path, eval_file: Path, specialist: Specialist, out_dir: Path) -> dict:
    """The specialist's share of the generalist's train/eval split (the same split, so no eval leaks)."""
    train, eval_ = read_jsonl(train_file), read_jsonl(eval_file)
    ecosystems = repo_ecosystems(train + eval_)
    counts = {}
    for name, samples in (("train", train), ("eval", eval_)):
        counts[name] = write_jsonl(out_dir / f"{name}.jsonl", select_samples(samples, specialist, ecosystems))
    return counts
