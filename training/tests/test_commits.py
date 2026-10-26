import subprocess
from pathlib import Path

from petru_train.commits import Commit, FileChange, commit_to_sample, iter_commits
from petru_train.samples import load_tools


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def commit_file(repo: Path, path: str, content: str, message: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "user.email", "t@t")
    commit_file(repo, "app.py", "print('v1')\n", "Add app entry point")
    commit_file(repo, "app.py", "print('v2')\n", "Print the second version string")
    commit_file(repo, "package-lock.json", "{}", "Add lockfile for the web client")
    commit_file(repo, "util.py", "x = 1\n", "wip")
    commit_file(repo, ".env", "API_KEY=abcdef\n", "Add environment configuration file")
    return repo


def test_iter_commits_keeps_only_clean_nontrivial_commits(tmp_path):
    commits = list(iter_commits(make_repo(tmp_path)))
    assert [c.message for c in commits] == ["Print the second version string", "Add app entry point"]
    second = commits[0]
    assert second.files == [FileChange("app.py", "print('v1')\n", "print('v2')\n", "python")]
    first = commits[1]
    assert first.files == [FileChange("app.py", None, "print('v1')\n", "python")]
    assert len(second.sha) == 40 and second.date


def test_secret_commits_are_dropped(tmp_path):
    repo = make_repo(tmp_path)
    commit_file(repo, "config.py", "KEY = 'sk-abcdefghijklmnopqrstuvwxyz1234'\n", "Add API configuration")
    assert "Add API configuration" not in [c.message for c in iter_commits(repo)]


def test_iter_commits_limits_files_and_size(tmp_path):
    repo = make_repo(tmp_path)
    for i in range(4):
        (repo / f"f{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Add four files at once")
    commit_file(repo, "big.py", "x = 1\n" * 2000, "Add a very large module")
    messages = [c.message for c in iter_commits(repo, max_files=3, max_file_chars=6000)]
    assert "Add four files at once" not in messages and "Add a very large module" not in messages


def test_commit_to_sample_has_read_then_write_then_complete():
    commit = Commit(
        sha="a" * 40,
        message="Print the second version string",
        files=[FileChange("app.py", "print('v1')\n", "print('v2')\n", "python")],
        date="2026-10-26T10:00:00+02:00",
    )
    sample = commit_to_sample(commit, repo_name="demo", license="MIT", tools=load_tools())
    assert sample.source == "commit" and sample.language == "python" and sample.commit == "a" * 40
    assert sample.messages[0]["role"] == "system" and sample.messages[1]["role"] == "user"
    assert (
        "Print the second version string" in sample.messages[1]["content"]
        and "app.py" in sample.messages[1]["content"]
    )
    calls = [c["function"]["name"] for m in sample.messages if m.get("tool_calls") for c in m["tool_calls"]]
    assert calls == ["read_file", "edit_file", "task_complete"]
    ids = [c["id"] for m in sample.messages if m.get("tool_calls") for c in m["tool_calls"]]
    tool_ids = [m["tool_call_id"] for m in sample.messages if m["role"] == "tool"]
    assert ids == tool_ids
    read_result = next(m for m in sample.messages if m["role"] == "tool")
    assert read_result["content"] == "print('v1')\n"


def test_commit_to_sample_uses_write_file_for_new_and_rewritten_files():
    new = Commit(
        "b" * 40, "Add util", [FileChange("util.py", None, "x = 1\n", "python")], "2026-01-01T00:00:00Z"
    )
    sample = commit_to_sample(new, "demo", "MIT", load_tools())
    calls = [c["function"]["name"] for m in sample.messages if m.get("tool_calls") for c in m["tool_calls"]]
    assert calls == ["read_file", "write_file", "task_complete"]
    assert "ERROR" in next(m for m in sample.messages if m["role"] == "tool")["content"]
    before = "\n".join(f"line {i}" for i in range(80)) + "\n"
    after = "\n".join(f"line {i}" if i % 2 else f"changed {i}" for i in range(80)) + "\n"
    rewritten = Commit(
        "c" * 40, "Rewrite", [FileChange("a.txt", before, after, None)], "2026-01-01T00:00:00Z"
    )
    sample = commit_to_sample(rewritten, "demo", "MIT", load_tools())
    calls = [c["function"]["name"] for m in sample.messages if m.get("tool_calls") for c in m["tool_calls"]]
    assert calls == ["read_file", "write_file", "task_complete"]
