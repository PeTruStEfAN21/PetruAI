import pytest

from petru.tools.base import ToolContext, ToolResult
from petru.tools.fs import edit_file, glob, grep, list_dir, read_file, write_file
from petru.tools.paths import OutsideProjectError, is_inside, resolve_in_project
from petru.tools.registry import default_registry


def ctx(root):
    return ToolContext(project_root=root, online=False)


def test_resolve_rejects_parent_escape_windows(tmp_path):
    with pytest.raises(OutsideProjectError):
        resolve_in_project("..\\..\\secret.txt", tmp_path)
    with pytest.raises(OutsideProjectError):
        resolve_in_project("C:\\Windows\\win.ini", tmp_path)
    assert resolve_in_project(".\\src\\x.ts", tmp_path) == (tmp_path / "src" / "x.ts").resolve()
    assert resolve_in_project("src/../a.py", tmp_path) == (tmp_path / "a.py").resolve()


def test_resolve_accepts_absolute_inside_root(tmp_path):
    target = tmp_path / "pkg" / "m.py"
    assert resolve_in_project(str(target), tmp_path) == target.resolve()
    assert is_inside(target, tmp_path) and not is_inside(tmp_path.parent, tmp_path)


def test_read_write_utf8_roundtrip(tmp_path):
    r = write_file.run({"path": "ș.txt", "content": "Țară și învățare\n"}, ctx(tmp_path))
    assert not r.is_error
    assert (tmp_path / "ș.txt").read_bytes().decode("utf-8") == "Țară și învățare\n"
    out = read_file.run({"path": "ș.txt"}, ctx(tmp_path)).output
    assert "1\tȚară și învățare" in out


def test_read_file_offset_limit_and_truncation_notice(tmp_path):
    (tmp_path / "big.txt").write_text("".join(f"line {i}\n" for i in range(1, 1001)), encoding="utf-8")
    out = read_file.run({"path": "big.txt", "offset": 10, "limit": 5}, ctx(tmp_path)).output
    assert out.splitlines()[0] == "10\tline 10" and "14\tline 14" in out
    assert "15\tline 15" not in out and "more lines" in out and "1000" in out


def test_read_file_missing_is_error(tmp_path):
    r = read_file.run({"path": "nope.py"}, ctx(tmp_path))
    assert r.is_error and "nope.py" in r.output


def test_outside_project_path_is_error_result(tmp_path):
    r = read_file.run({"path": "..\\x.txt"}, ctx(tmp_path))
    assert r.is_error and "outside" in r.output.lower()


def test_write_file_creates_parents(tmp_path):
    write_file.run({"path": "a/b/c.py", "content": "x = 1\n"}, ctx(tmp_path))
    assert (tmp_path / "a" / "b" / "c.py").read_text(encoding="utf-8") == "x = 1\n"


def test_edit_file_exact_and_whitespace_tolerant(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return  1\n", encoding="utf-8")
    r = edit_file.run({"path": "a.py", "old": "return  1", "new": "return 2"}, ctx(tmp_path))
    assert not r.is_error and (tmp_path / "a.py").read_text(encoding="utf-8") == "def f():\n    return 2\n"
    r2 = edit_file.run(
        {"path": "a.py", "old": "def f():\n  return 2", "new": "def g():\n    return 3"}, ctx(tmp_path)
    )
    assert not r2.is_error and "def g():\n    return 3\n" == (tmp_path / "a.py").read_text(encoding="utf-8")


def test_edit_file_ambiguous_match_errors(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    r = edit_file.run({"path": "a.py", "old": "x = 1", "new": "x = 2"}, ctx(tmp_path))
    assert r.is_error and "found 2 matches" in r.output
    r2 = edit_file.run({"path": "a.py", "old": "nope", "new": "y"}, ctx(tmp_path))
    assert r2.is_error and "found 0 matches" in r2.output
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\nx = 1\n"


def test_edit_file_replace_all(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    r = edit_file.run({"path": "a.py", "old": "x = 1", "new": "x = 2", "replace_all": True}, ctx(tmp_path))
    assert not r.is_error and (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 2\nx = 2\n"


def test_list_dir_skips_ignored_and_marks_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("hi", encoding="utf-8")
    out = list_dir.run({"path": "."}, ctx(tmp_path)).output.splitlines()
    assert "src/" in out and "README.md" in out
    assert not any(e.startswith("node_modules") or e.startswith(".git") for e in out)


def test_glob_and_grep_return_relative_paths(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("def alpha():\n    return 'beta'\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("alpha\n", encoding="utf-8")
    g = glob.run({"pattern": "**/*.py"}, ctx(tmp_path)).output.splitlines()
    assert g == ["pkg/m.py"]
    r = grep.run({"pattern": "alpha"}, ctx(tmp_path)).output.splitlines()
    assert r == ["pkg/m.py:1: def alpha():"]


def test_grep_with_glob_filter_and_max_results(tmp_path):
    (tmp_path / "a.py").write_text("hit\nhit\nhit\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("hit\n", encoding="utf-8")
    out = grep.run({"pattern": "hit", "glob": "*.py", "max_results": 2}, ctx(tmp_path)).output
    lines = out.splitlines()
    assert lines[:2] == ["a.py:1: hit", "a.py:2: hit"] and "b.txt" not in out and "truncated" in out.lower()


def test_registry_schemas_are_openai_shaped():
    reg = default_registry(ctx_online=False)
    names = reg.names()
    assert {"read_file", "write_file", "edit_file", "list_dir", "glob", "grep"} <= set(names)
    for schema in reg.schemas():
        assert schema["type"] == "function"
        assert schema["function"]["parameters"]["type"] == "object"
        assert schema["function"]["name"] in names
    assert reg.get("read_file").mutating is False and reg.get("write_file").mutating is True
    assert reg.get("missing") is None
    assert [s["function"]["name"] for s in reg.schemas(["grep"])] == ["grep"]
    assert isinstance(ToolResult("x"), ToolResult)


def test_write_file_can_build_a_large_file_in_parts(tmp_path):
    write_file.run({"path": "big.py", "content": "a = 1\n"}, ctx(tmp_path))
    r = write_file.run({"path": "big.py", "content": "b = 2\n", "append": True}, ctx(tmp_path))
    assert not r.is_error and (tmp_path / "big.py").read_text(encoding="utf-8") == "a = 1\nb = 2\n"
