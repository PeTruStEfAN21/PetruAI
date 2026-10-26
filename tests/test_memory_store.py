import re
from datetime import date

import pytest

from petru.memory.store import MEMORY_TYPES, MemoryStore, memory_dir, petru_home, slugify


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PETRU_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_scopes_resolve_to_project_and_home(tmp_path, home):
    assert petru_home() == home
    assert memory_dir("project", tmp_path / "p") == tmp_path / "p" / ".petru" / "memory"
    assert memory_dir("global", tmp_path / "p") == home / "memory"
    assert MEMORY_TYPES == ("user", "feedback", "project", "reference")


def test_new_memory_writes_file_with_frontmatter_and_one_index_line(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    memory = store.remember("Test runner", "pytest with -q", "project", "The project uses pytest -q.")
    text = memory.path.read_text(encoding="utf-8")
    assert memory.path.name == "test-runner.md"
    assert text.startswith("---\nname: Test runner\ndescription: pytest with -q\ntype: project\n---\n")
    assert "The project uses pytest -q." in text
    assert store.index_text().splitlines() == ["- [Test runner](test-runner.md) — pytest with -q"]


def test_remembering_again_appends_a_dated_bullet_and_keeps_one_index_line(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    store.remember("Style", "short functions", "feedback", "Prefer short functions.")
    memory = store.remember("Style", "short functions, no globals", "feedback", "Avoid module globals.")
    body = memory.path.read_text(encoding="utf-8")
    assert (
        "Prefer short functions." in body and f"- {date.today().isoformat()}: Avoid module globals." in body
    )
    assert store.index_text().splitlines() == ["- [Style](style.md) — short functions, no globals"]
    assert store.get("Style").description == "short functions, no globals"


@pytest.mark.parametrize("name", ["../x", "a/b", "con", "Ăla bună!", "...", "x" * 200])
def test_memory_slug_is_safe(tmp_path, name):
    slug = slugify(name)
    assert re.fullmatch(r"[a-z0-9-]{1,60}", slug) and slug not in {"con", "prn", "aux", "nul"}
    store = MemoryStore(tmp_path / "mem")
    memory = store.remember(name, "d", "user", "c")
    assert memory.path.parent == tmp_path / "mem"


def test_index_is_capped_but_files_are_kept(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    for i in range(205):
        store.remember(f"fact {i}", f"d{i}", "reference", "c")
    lines = store.index_text().splitlines()
    assert len(lines) == 200 and lines[0].startswith("- [fact 5]") and lines[-1].startswith("- [fact 204]")
    assert len(store.all()) == 205


def test_invalid_type_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="type"):
        MemoryStore(tmp_path / "mem").remember("x", "d", "opinion", "c")


def test_forget_removes_file_and_index_line(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    memory = store.remember("Tmp", "d", "user", "c")
    assert store.forget("Tmp") and not memory.path.exists() and store.index_text() == ""
    assert store.forget("Tmp") is False and store.get("Tmp") is None
