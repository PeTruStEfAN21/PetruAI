import pytest

from petru.agent.context import build_system_prompt, estimate_tokens
from petru.agent.permissions import decide
from petru.agent.state import Phase, Session
from petru.memory.store import MemoryStore, memory_dir
from petru.memory.tools import RecallTool, RememberTool, memory_prompt_section
from petru.tools.base import ToolContext
from petru.tools.registry import default_registry
from petru.tui.commands import HELP_TEXT, Command, parse_command


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PETRU_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def ctx(root):
    return ToolContext(root, False, None, Session(root))


def test_remember_writes_to_the_requested_scope(tmp_path):
    project = tmp_path / "p"
    r = RememberTool().run(
        {"name": "Tests", "description": "pytest -q", "type": "project", "content": "Use pytest -q."},
        ctx(project),
    )
    assert not r.is_error and "Tests" in r.output
    assert MemoryStore(memory_dir("project", project)).get("Tests") is not None
    RememberTool().run(
        {
            "name": "Lang",
            "description": "Romanian",
            "type": "user",
            "content": "Answer in Romanian.",
            "scope": "global",
        },
        ctx(project),
    )
    assert MemoryStore(memory_dir("global", project)).get("Lang").body == "Answer in Romanian."


def test_remember_rejects_secrets_and_bad_types(tmp_path):
    bad = RememberTool().run(
        {"name": "k", "description": "d", "type": "opinion", "content": "c"}, ctx(tmp_path)
    )
    assert bad.is_error and "type" in bad.output
    secret = RememberTool().run(
        {
            "name": "key",
            "description": "d",
            "type": "reference",
            "content": "API_KEY=sk-abcdefghijklmnopqrstuvwx",
        },
        ctx(tmp_path),
    )
    assert secret.is_error and "secret" in secret.output.lower()


def test_secret_filter_allows_advice_about_passwords(tmp_path):
    advice = RememberTool().run(
        {
            "name": "auth",
            "description": "d",
            "type": "feedback",
            "content": "password: hash with bcrypt, never log it",
        },
        ctx(tmp_path),
    )
    assert not advice.is_error
    for secret in ("password=Sup3rS3cretValue", "token: 'ghp_abcdefghijklmnop'", "api_key = abcdef123456"):
        r = RememberTool().run(
            {"name": "s", "description": "d", "type": "reference", "content": secret}, ctx(tmp_path)
        )
        assert r.is_error, secret


def test_changing_the_type_of_a_memory_is_reported(tmp_path):
    RememberTool().run({"name": "Db", "description": "d", "type": "project", "content": "a"}, ctx(tmp_path))
    r = RememberTool().run(
        {"name": "Db", "description": "d", "type": "feedback", "content": "b"}, ctx(tmp_path)
    )
    assert "type changed from project to feedback" in r.output


def test_recall_returns_body_or_not_found(tmp_path):
    RememberTool().run(
        {"name": "Db", "description": "sqlite", "type": "project", "content": "SQLite file."}, ctx(tmp_path)
    )
    assert "SQLite file." in RecallTool().run({"name": "Db"}, ctx(tmp_path)).output
    missing = RecallTool().run({"name": "Nope", "scope": "global"}, ctx(tmp_path))
    assert not missing.is_error and "No memory" in missing.output


def test_memory_section_has_both_indexes_and_respects_the_budget(tmp_path):
    for i in range(400):
        MemoryStore(memory_dir("project", tmp_path)).remember(f"fact {i}", "x" * 40, "reference", "c")
    MemoryStore(memory_dir("global", tmp_path)).remember("Lang", "Romanian answers", "user", "c")
    section = memory_prompt_section(tmp_path, max_tokens=1500)
    assert "## Memory (global)" in section and "Lang" in section and "## Memory (project)" in section
    assert estimate_tokens(section) <= 1500 and "fact 399" in section  # newest kept


def test_system_prompt_includes_memory(tmp_path):
    MemoryStore(memory_dir("project", tmp_path)).remember("Tests", "pytest -q", "project", "c")
    assert "[Tests](tests.md)" in build_system_prompt(Session(tmp_path), tmp_path, online=True)


def test_memory_tools_registered_and_allowed_in_design(tmp_path):
    registry = default_registry(ctx_online=False)
    session = Session(tmp_path, phase=Phase.DESIGN)
    for name in ("remember", "recall"):
        tool = registry.get(name)
        assert tool is not None and decide(tool, {"name": "x"}, session).kind == "allow"
    assert decide(registry.get("write_file"), {"path": "a"}, session).kind == "deny"


def test_memory_command_parses():
    assert parse_command("/memory") == Command("memory", "") and "/memory" in HELP_TEXT
