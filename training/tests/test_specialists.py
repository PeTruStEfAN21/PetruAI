from pathlib import Path

from petru_train.samples import Sample, read_jsonl, write_jsonl
from petru_train.specialists import (
    Specialist,
    load_specialists,
    repo_ecosystems,
    select_samples,
    write_specialist_data,
)

PYTHON = Specialist("python", languages=["python"], tasks=["python"])
WEB = Specialist("web", languages=["typescript", "javascript"], tasks=["ts"])


def sample(sid: str, repo: str, language: str, source: str = "commit") -> Sample:
    return Sample(sid, source, repo, "MIT", "abc", language, [{"role": "user", "content": sid}], [])


def corpus() -> list[Sample]:
    return [
        sample("flask:1", "flask", "python"),
        sample("flask:2", "flask", "python"),
        sample("flask:docs", "flask", "markdown"),
        sample("express:1", "express", "typescript"),
        sample("express:ci", "express", "yaml"),
        sample("misc:readme", "misc", "markdown"),  # a repo with no code samples: no ecosystem
        sample("traj:python_todo", "petru", "python", source="trajectory"),
    ]


def test_a_repo_belongs_to_its_dominant_code_language():
    assert repo_ecosystems(corpus()) == {"flask": "python", "express": "typescript", "petru": "python"}


def test_a_specialist_gets_its_languages_and_the_docs_of_its_ecosystem():
    samples = corpus()
    ecosystems = repo_ecosystems(samples)
    assert [s.id for s in select_samples(samples, PYTHON, ecosystems)] == [
        "flask:1", "flask:2", "flask:docs", "traj:python_todo",
    ]  # fmt: skip
    assert [s.id for s in select_samples(samples, WEB, ecosystems)] == ["express:1", "express:ci"]


def test_specialist_data_keeps_the_generalist_split(tmp_path):
    write_jsonl(tmp_path / "train.jsonl", [s for s in corpus() if s.id != "flask:2"])
    write_jsonl(tmp_path / "eval.jsonl", [sample("flask:2", "flask", "python")])
    counts = write_specialist_data(tmp_path / "train.jsonl", tmp_path / "eval.jsonl", PYTHON, tmp_path / "py")
    assert counts == {"train": 3, "eval": 1}
    assert [s.id for s in read_jsonl(tmp_path / "py" / "eval.jsonl")] == ["flask:2"]


def test_load_specialists_reads_the_config(tmp_path):
    path = tmp_path / "specialists.toml"
    path.write_text(
        '[[specialist]]\nname = "python"\nlanguages = ["python"]\ntasks = ["python"]\nepochs = 3\n\n'
        '[[specialist]]\nname = "web"\nlanguages = ["typescript"]\ntasks = ["ts"]\n',
        encoding="utf-8",
    )
    specialists = load_specialists(path)
    assert [s.name for s in specialists] == ["python", "web"]
    assert specialists[0].epochs == 3.0 and specialists[1].epochs == Specialist("x", [], []).epochs


def test_the_committed_config_covers_the_three_stacks():
    names = {s.name: s for s in load_specialists()}
    assert set(names) >= {"python", "web", "flutter"}
    assert names["flutter"].languages == ["dart"] and "ts" in names["web"].tasks
    tasks = Path(__file__).resolve().parents[1] / "tasks"
    for name in ("python", "web", "flutter"):  # the stacks that already have harness tasks
        assert any(tasks.glob(f"{prefix}_*.toml") for prefix in names[name].tasks), name
    claimed = [language for s in names.values() for language in s.languages]
    assert len(claimed) == len(set(claimed))  # a language belongs to one specialist
