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


def test_assistant_tool_config_paths_are_excluded():
    for path in [
        ".assistant/settings.json",
        ".cursor/rules.md",
        "docs/plans/x.md",
        ".plans/a",
    ]:
        assert is_generated_path(path), path


def test_is_trivial_message():
    assert is_trivial_message("wip")
    assert is_trivial_message("  Update  ")
    assert is_trivial_message("fix")
    assert is_trivial_message("x")
    assert not is_trivial_message("Add JSON storage for todos")
    assert not is_trivial_message("fix: handle empty input in parser")
