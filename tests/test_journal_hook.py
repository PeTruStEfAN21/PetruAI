import subprocess
import time
from pathlib import Path

from petru.agent.context import build_system_prompt
from petru.agent.state import Session
from petru.journal.hook import HOOK_MARK, hook_script, install_hook, uninstall_hook
from petru.journal.store import Journal
from petru.journal.summarize import summarize_pending
from petru.tui.commands import HELP_TEXT, Command, parse_command
from tests.fakes import FakeProvider, result

REPO_ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")


def make_repo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "user.email", "t@t")
    return repo


def commit(repo, name, text, message):
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    return git(repo, "commit", "-q", "-m", message)


def test_hook_script_never_fails_the_commit(tmp_path):
    repo = make_repo(tmp_path)
    install_hook(repo, repo_root=tmp_path / "no-such-petru")
    done = commit(repo, "a.py", "x = 1\n", "Add a module")
    assert done.returncode == 0, done.stderr
    assert git(repo, "log", "--oneline").stdout.strip()


def test_install_keeps_an_existing_hook_and_uninstall_restores_it(tmp_path):
    repo = make_repo(tmp_path)
    hooks = repo / ".git" / "hooks"
    (hooks / "post-commit").write_text("#!/bin/sh\necho user hook\n", encoding="utf-8")
    install_hook(repo, repo_root=REPO_ROOT)
    assert (hooks / "post-commit.user").read_text(encoding="utf-8") == "#!/bin/sh\necho user hook\n"
    ours = (hooks / "post-commit").read_text(encoding="utf-8")
    assert HOOK_MARK in ours and "post-commit.user" in ours
    install_hook(repo, repo_root=REPO_ROOT)  # idempotent: the user hook is not overwritten by ours
    assert "echo user hook" in (hooks / "post-commit.user").read_text(encoding="utf-8")
    uninstall_hook(repo)
    assert (hooks / "post-commit").read_text(encoding="utf-8") == "#!/bin/sh\necho user hook\n"
    assert not (hooks / "post-commit.user").exists()


def test_hook_script_points_at_the_petru_checkout():
    script = hook_script(Path("C:/tools/PetruAI"))
    assert script.startswith("#!/bin/sh\n") and HOOK_MARK in script
    assert (
        '--project "C:/tools/PetruAI"' in script
        and "|| true" in script
        and script.rstrip().endswith("exit 0")
    )
    assert "uv run --no-sync" in script  # a background hook must never re-sync the agent's environment


def test_a_real_commit_is_queued(tmp_path):
    repo = make_repo(tmp_path)
    install_hook(repo, repo_root=REPO_ROOT)
    commit(repo, "a.py", "x = 1\n", "Add a module")
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    db = repo / ".petru" / "journal.sqlite"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if db.is_file() and [s for s, _ in Journal(db).pending_commits()] == [sha]:
            break
        time.sleep(0.5)
    assert db.is_file() and [s for s, _ in Journal(db).pending_commits()] == [sha]


def test_summarize_pending_stores_summaries_once(tmp_path):
    repo = make_repo(tmp_path)
    commit(repo, "a.py", "x = 1\n", "Add a module")
    commit(repo, "a.py", "x = 2\n", "Change the value")
    shas = git(repo, "log", "--format=%H").stdout.split()
    journal = Journal(repo / ".petru" / "journal.sqlite")
    for sha in reversed(shas):
        journal.enqueue_commit(sha)
    provider = FakeProvider([result(content="Added a.py.\n"), result(content="Changed x to 2.\nNo tests.\n")])
    assert summarize_pending(repo, provider) == 2
    assert summarize_pending(repo, provider) == 0
    assert [s for _, s in journal.recent_summaries()] == ["Changed x to 2.\nNo tests.", "Added a.py."]
    prompt = provider.calls[1]["messages"][-1]["content"]
    assert "Change the value" in prompt and "-x = 1" in prompt and "+x = 2" in prompt


def test_empty_summary_is_not_retried_forever_and_notify_announces_work(tmp_path):
    repo = make_repo(tmp_path)
    commit(repo, "a.py", "x = 1\n", "Add a module")
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    journal = Journal(repo / ".petru" / "journal.sqlite")
    journal.enqueue_commit(sha)
    announced = []
    assert summarize_pending(repo, FakeProvider([result(content="  ")]), notify=announced.append) == 0
    assert announced == [1] and journal.pending_commits() == [] and journal.recent_summaries() == []
    assert summarize_pending(repo, FakeProvider([]), notify=announced.append) == 0 and announced == [1]


def test_system_prompt_shows_recent_commit_summaries(tmp_path):
    journal = Journal(tmp_path / ".petru" / "journal.sqlite")
    journal.enqueue_commit("a" * 40)
    journal.set_summary("a" * 40, "Added login.\nTests pass.")
    text = build_system_prompt(Session(tmp_path), tmp_path, online=True)
    assert "## Recent commits" in text and "aaaaaaa: Added login. Tests pass." in text


def test_no_journal_means_no_section_and_no_file(tmp_path):
    assert "Recent commits" not in build_system_prompt(Session(tmp_path), tmp_path, online=True)
    assert not (tmp_path / ".petru").exists()


def test_journal_command_parses():
    assert parse_command("/journal") == Command("journal", "") and "/journal" in HELP_TEXT
