"""Robustness against the local server's limits: exact token counts, context overflow, repository hygiene."""

import subprocess

from petru.agent.context import compact_if_needed
from petru.agent.state import Session
from petru.providers.openai_compat import OpenAICompatProvider
from petru.tools.base import ToolContext
from petru.tools.git import DEFAULT_GITIGNORE, ensure_repo, git
from petru.tui.port import ScriptedUI
from tests.fakes import FakeOpenAIClient, FakeProvider, make_agent, result

SUMMARY = "[Summary of earlier conversation]"


def test_provider_count_tokens_uses_tokenize_endpoint():
    posts = []

    def http_post(url, payload, timeout):
        posts.append((url, payload))
        return {"tokens": [1, 2, 3, 4]}

    provider = OpenAICompatProvider(
        "http://127.0.0.1:8080/v1", client=FakeOpenAIClient([]), http_post=http_post
    )
    assert provider.count_tokens("hello world") == 4
    assert posts == [("http://127.0.0.1:8080/tokenize", {"content": "hello world"})]


def test_provider_count_tokens_returns_none_when_server_fails():
    def http_post(url, payload, timeout):
        raise OSError("down")

    provider = OpenAICompatProvider(
        "http://127.0.0.1:8080/v1", client=FakeOpenAIClient([]), http_post=http_post
    )
    assert provider.count_tokens("x") is None


class CountingProvider(FakeProvider):
    """Reports one token per character: four times the chars/4 estimate."""

    def count_tokens(self, text):
        return len(text)


def test_compaction_uses_the_provider_token_count(tmp_path):
    provider = CountingProvider([result(content="summary")])
    session = Session(tmp_path)
    session.messages = [
        {"role": "user", "content": "a" * 600},
        {"role": "assistant", "content": "b" * 600},
    ] * 2
    assert (
        compact_if_needed(session, provider, ctx_tokens=6000) is True
    )  # estimate says 600 tokens, counter 2400
    assert SUMMARY in session.messages[0]["content"]


def test_forced_compaction_summarizes_even_under_budget(tmp_path):
    provider = FakeProvider([result(content="summary")])
    session = Session(tmp_path)
    session.messages = [
        {"role": "user", "content": "short"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "next"},
    ]
    assert compact_if_needed(session, provider, ctx_tokens=100000, force=True) is True
    assert session.messages[0]["content"].startswith(SUMMARY) and session.messages[-1]["content"] == "next"


class OverflowOnceProvider(FakeProvider):
    def __init__(self, scripted):
        super().__init__(scripted)
        self.failed = False

    def complete(self, messages, tools, on_text=None, temperature=0.2, max_tokens=4096, **kwargs):
        if (
            tools is not None and not self.failed
        ):  # the first agent request overflows; the summary request has no tools
            self.failed = True
            raise RuntimeError("Error code: 400 - request (56824 tokens) exceeds the available context size")
        return super().complete(messages, tools, on_text, temperature, max_tokens)


def test_context_overflow_compacts_before_the_retry(tmp_path):
    provider = OverflowOnceProvider([result(content="summary"), result(content="ok")])
    agent = make_agent(provider, ScriptedUI(), tmp_path)
    agent.session.messages = [
        {"role": "user", "content": "old " * 50},
        {"role": "assistant", "content": "older"},
    ]
    assert agent.run_turn("x") == "ok" and agent.stop_reason is None
    assert any(SUMMARY in m.get("content", "") for m in provider.calls[-1]["messages"])


def tracked(repo):
    out = subprocess.run(["git", "ls-files"], cwd=str(repo), capture_output=True, text=True, encoding="utf-8")
    return out.stdout.split()


def test_git_commit_writes_a_default_gitignore_first(tmp_path):
    ensure_repo(tmp_path)
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "i.js").write_text("1", encoding="utf-8")
    (tmp_path / "a.js").write_text("1", encoding="utf-8")
    r = git.run({"action": "commit", "message": "init"}, ToolContext(tmp_path, False))
    assert not r.is_error and "node_modules/" in DEFAULT_GITIGNORE
    assert ".petru/index.sqlite*" in DEFAULT_GITIGNORE and ".petru/journal.sqlite*" in DEFAULT_GITIGNORE
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == DEFAULT_GITIGNORE
    assert sorted(tracked(tmp_path)) == [".gitignore", "a.js"]


def test_git_commit_keeps_an_existing_gitignore(tmp_path):
    ensure_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("custom\n", encoding="utf-8")
    (tmp_path / "a.js").write_text("1", encoding="utf-8")
    git.run({"action": "commit", "message": "init"}, ToolContext(tmp_path, False))
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "custom\n"


def node_project(root):
    ensure_repo(root)
    (root / "node_modules" / "x").mkdir(parents=True)
    (root / "node_modules" / "x" / "i.js").write_text("1", encoding="utf-8")
    (root / "a.js").write_text("1", encoding="utf-8")


def test_git_add_writes_the_default_gitignore_before_staging(tmp_path):
    node_project(tmp_path)
    ctx = ToolContext(tmp_path, False)
    git.run({"action": "add"}, ctx)
    git.run({"action": "commit", "message": "init"}, ctx)
    assert sorted(tracked(tmp_path)) == [".gitignore", "a.js"]


def test_git_commit_unstages_what_the_new_gitignore_excludes(tmp_path):
    node_project(tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True)  # staged by a shell command
    r = git.run({"action": "commit", "message": "init"}, ToolContext(tmp_path, False))
    assert not r.is_error and sorted(tracked(tmp_path)) == [".gitignore", "a.js"]


def test_git_commit_never_untracks_files_committed_before(tmp_path):
    node_project(tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-qm", "old"], cwd=str(tmp_path), capture_output=True)
    (tmp_path / "b.js").write_text("2", encoding="utf-8")
    git.run({"action": "commit", "message": "next"}, ToolContext(tmp_path, False))
    assert "node_modules/x/i.js" in tracked(tmp_path) and "b.js" in tracked(tmp_path)


def test_git_commit_output_stays_small(tmp_path):
    ensure_repo(tmp_path)
    for i in range(400):
        (tmp_path / f"file_{i:03}.txt").write_text("x", encoding="utf-8")
    r = git.run({"action": "commit", "message": "many files"}, ToolContext(tmp_path, False))
    assert not r.is_error and len(r.output) < 5000 and "many files" in r.output
