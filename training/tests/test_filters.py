import pytest

from petru_train.filters import has_secret, is_generated_path, is_trivial_message, language_of


@pytest.mark.parametrize(
    "path,expected",
    [
        ("package-lock.json", True),
        ("app/pubspec.lock", True),
        ("dist/bundle.js", True),
        ("web/static/app.min.js", True),
        ("node_modules/x/index.js", True),
        ("lib/models/user.g.dart", True),
        ("api/migrations/0001_initial.py", True),
        ("assets/logo.png", True),
        ("src/app.py", False),
        ("lib/main.dart", False),
        ("README.md", False),
        ("tests/test_app.py", False),
    ],
)
def test_generated_paths_are_excluded(path, expected):
    assert is_generated_path(path) is expected


def test_has_secret():
    assert has_secret("-----BEGIN RSA PRIVATE KEY-----\nMIIE...")
    assert has_secret("OPENAI_KEY = sk-abcdefghijklmnopqrstuvwxyz1234")
    assert has_secret("api_key = 'x'")
    assert has_secret("token = 'QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVowMTIzNDU2Nzg5'")  # 40+ base64 chars
    assert not has_secret("def add(a, b):\n    return a + b\n")
    assert not has_secret("digest = 'QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVow'")  # 36 chars, under the limit


def test_language_of():
    assert language_of("src/app.py") == "python"
    assert language_of("src/App.tsx") == "typescript"
    assert language_of("lib/main.dart") == "dart"
    assert language_of("scripts/build.ps1") == "powershell"
    assert language_of("db/schema.sql") == "sql"
    assert language_of("docs/notes.md") == "markdown"
    assert language_of("bin/tool") is None
    assert language_of("image.png") is None


@pytest.mark.parametrize(
    "message,expected",
    [
        ("build(deps): Bump actions/checkout from 4 to 7 (#3)", True),
        ("chore(deps-dev): bump vitest to 2.1.9", True),
        ("Bump the npm-minor-patch group with 2 updates", True),
        ("Update httpcore requirement from <0.17.0 to <0.18.0", True),
        ("chore(release): 3.2.0", True),
        ("v1.4.2", True),
        ("Version Packages", True),
        ("Add JSON storage for todos", False),
        ("Fix version parsing in the CLI", False),
    ],
)
def test_is_bump_message(message, expected):
    from petru_train.filters import is_bump_message

    assert is_bump_message(message) is expected


def test_hidden_tool_folders_are_excluded_but_github_is_kept():
    for path in [".cursor/rules.md", ".anytool/settings.json", "app/.cache/x.py", ".idea/workspace.xml"]:
        assert is_generated_path(path), path
    assert not is_generated_path(".github/workflows/ci.yml")
    assert not is_generated_path("src/.hidden_name.py")  # a hidden file is not a hidden folder


def test_planning_documents_are_excluded_but_other_docs_are_kept():
    for path in ["docs/tool/plans/2026-01-01-x.md", "docs/specs/design.md"]:
        assert is_generated_path(path), path
    assert not is_generated_path("docs/guide.md") and not is_generated_path("src/plans/route.py")


def test_is_trivial_message():
    assert is_trivial_message("wip")
    assert is_trivial_message("  Update  ")
    assert is_trivial_message("fix")
    assert is_trivial_message("x")
    assert not is_trivial_message("Add JSON storage for todos")
    assert not is_trivial_message("fix: handle empty input in parser")


def test_every_in_demand_language_has_a_label():
    from petru_train.filters import language_of

    expected = {
        "a.php": "php", "a.rb": "ruby", "a.swift": "swift", "a.scala": "scala", "a.R": "r", "a.kts": "kotlin",
        "a.cxx": "cpp", "a.hh": "cpp", "a.vue": "javascript", "a.svelte": "javascript", "a.bash": "shell",
        "a.psm1": "powershell", "a.lua": "lua", "a.ex": "elixir", "a.exs": "elixir",
    }  # fmt: skip
    assert {path: language_of(path) for path in expected} == expected
