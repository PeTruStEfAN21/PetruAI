import zipfile

import pytest

from petru import cli
from petru.memory.store import MemoryStore, memory_dir
from petru.memory.transfer import export_memory, import_memory


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PETRU_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def seed(project):
    MemoryStore(memory_dir("global", project)).remember("Lang", "Romanian", "user", "Answer in Romanian.")
    MemoryStore(memory_dir("project", project)).remember("Db", "sqlite", "project", "SQLite file.")
    (project / ".petru").mkdir(parents=True, exist_ok=True)
    (project / ".petru" / "DECISIONS.md").write_text("# Decizii\n\n- 2026-10-26: x -> y\n", encoding="utf-8")
    (project / ".petru" / "journal.sqlite").write_bytes(b"sqlite-bytes")
    (project / ".petru" / "index.sqlite").write_bytes(b"never exported")


def test_export_layout_and_flags(tmp_path, home):
    project = tmp_path / "p"
    seed(project)
    count = export_memory(tmp_path / "all.zip", project)
    names = set(zipfile.ZipFile(tmp_path / "all.zip").namelist())
    assert count == len(names)
    assert {"global/MEMORY.md", "global/lang.md", "project/memory/MEMORY.md", "project/memory/db.md",
            "project/DECISIONS.md", "project/journal.sqlite"} <= names  # fmt: skip
    assert not any("index" in n for n in names)
    export_memory(tmp_path / "g.zip", project, include_project=False)
    assert all(n.startswith("global/") for n in zipfile.ZipFile(tmp_path / "g.zip").namelist())
    export_memory(tmp_path / "p.zip", project, include_global=False)
    assert all(n.startswith("project/") for n in zipfile.ZipFile(tmp_path / "p.zip").namelist())


def test_round_trip_into_an_empty_home_and_project(tmp_path, home, monkeypatch):
    seed(tmp_path / "p")
    export_memory(tmp_path / "all.zip", tmp_path / "p")
    monkeypatch.setenv("PETRU_HOME", str(tmp_path / "home2"))
    target = tmp_path / "q"
    counts = import_memory(tmp_path / "all.zip", target)
    assert counts["added"] >= 4 and counts["merged"] == 0
    assert MemoryStore(memory_dir("global", target)).get("Lang").body == "Answer in Romanian."
    assert MemoryStore(memory_dir("project", target)).get("Db").body == "SQLite file."
    assert "x -> y" in (target / ".petru" / "DECISIONS.md").read_text(encoding="utf-8")


def test_import_merges_bullets_into_existing_memories(tmp_path, home):
    seed(tmp_path / "p")
    export_memory(tmp_path / "all.zip", tmp_path / "p")
    target = tmp_path / "q"
    MemoryStore(memory_dir("project", target)).remember("Db", "postgres", "project", "Postgres in prod.")
    counts = import_memory(tmp_path / "all.zip", target)
    body = MemoryStore(memory_dir("project", target)).get("Db").body
    assert counts["merged"] >= 1 and "Postgres in prod." in body and "SQLite file." in body


def test_import_is_idempotent(tmp_path, home):
    seed(tmp_path / "p")
    export_memory(tmp_path / "all.zip", tmp_path / "p")
    target = tmp_path / "q"
    import_memory(tmp_path / "all.zip", target)
    first = {p.name: p.read_text(encoding="utf-8") for p in memory_dir("project", target).iterdir()}
    decisions = (target / ".petru" / "DECISIONS.md").read_text(encoding="utf-8")
    counts = import_memory(tmp_path / "all.zip", target)
    again = {p.name: p.read_text(encoding="utf-8") for p in memory_dir("project", target).iterdir()}
    assert again == first and counts["added"] == 0
    assert (target / ".petru" / "DECISIONS.md").read_text(encoding="utf-8") == decisions


def test_import_rejects_paths_outside_the_layout(tmp_path, home):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../evil.md", "x")
        zf.writestr("project/memory/../../../evil2.md", "x")
    counts = import_memory(bad, tmp_path / "q")
    assert (
        counts["skipped"] == 2
        and not (tmp_path / "evil.md").exists()
        and not (tmp_path / "evil2.md").exists()
    )


def test_cli_subcommands_and_old_flags(tmp_path, home, capsys):
    seed(tmp_path / "p")
    zip_path = tmp_path / "m.zip"
    assert cli.run_subcommand(["memory", "export", str(zip_path), "--project", str(tmp_path / "p")]) == 0
    assert zip_path.exists()
    assert cli.run_subcommand(["memory", "import", str(zip_path), "--project", str(tmp_path / "q")]) == 0
    assert "imported" in capsys.readouterr().out.lower()
    assert cli.run_subcommand(["-p", "hello"]) is None and cli.run_subcommand([]) is None
