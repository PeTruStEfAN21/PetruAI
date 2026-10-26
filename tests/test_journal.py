import threading
import time

from petru import cli
from petru.journal.store import Journal
from petru.journal.watcher import ProjectWatcher


def test_create_modify_delete_produce_events_with_diffs(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    created = journal.record_change("a.py", "x = 1\n")
    assert created.kind == "created" and "+x = 1" in created.diff
    modified = journal.record_change("a.py", "x = 2\n")
    assert modified.kind == "modified" and "-x = 1" in modified.diff and "+x = 2" in modified.diff
    assert journal.record_change("a.py", "x = 2\n") is None  # an unchanged save is not an event
    deleted = journal.record_change("a.py", None)
    assert deleted.kind == "deleted" and "-x = 2" in deleted.diff
    assert journal.record_change("a.py", None) is None
    assert [e.kind for e in journal.recent_events()] == ["created", "modified", "deleted"]


def test_snapshot_all_makes_first_edit_a_modification(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    journal = Journal(tmp_path / "j.sqlite")
    assert journal.snapshot_all(root) == 1 and journal.recent_events() == []
    assert journal.record_change("a.py", "x = 3\n").kind == "modified"


def test_journal_concurrent_writers(tmp_path):
    db = tmp_path / "j.sqlite"
    Journal(db)  # create the schema once
    errors = []

    def writer(tag):
        try:
            journal = Journal(db)
            for i in range(200):
                journal.record_change(f"{tag}/{i}.txt", f"{tag} {i}\n")
        except Exception as exc:  # pragma: no cover - the assertion below reports it
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(tag,)) for tag in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(Journal(db).recent_events(limit=1000)) == 400


def test_commit_queue_and_summaries(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    journal.enqueue_commit("abc123")
    journal.enqueue_commit("abc123")  # idempotent
    journal.enqueue_commit("def456")
    assert [sha for sha, _ in journal.pending_commits()] == ["abc123", "def456"]
    journal.set_summary("abc123", "Added login.\nTests pass.")
    assert [sha for sha, _ in journal.pending_commits()] == ["def456"]
    assert journal.recent_summaries(5) == [("abc123", "Added login.\nTests pass.")]


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def test_watcher_records_saves_and_skips_ignored_folders(tmp_path):
    root = tmp_path / "p"
    (root / "node_modules").mkdir(parents=True)
    journal = Journal(tmp_path / "j.sqlite")
    watcher = ProjectWatcher(root, journal, debounce_s=0.2)
    watcher.start()
    try:
        (root / "node_modules" / "x.js").write_text("1", encoding="utf-8")
        (root / "app.py").write_text("print(1)\n", encoding="utf-8")
        assert wait_for(lambda: any(e.path == "app.py" for e in journal.recent_events()))
        (root / "app.py").write_text("print(2)\n", encoding="utf-8")
        assert wait_for(lambda: len([e for e in journal.recent_events() if e.path == "app.py"]) == 2)
    finally:
        watcher.stop()
    assert not any(e.path.startswith("node_modules") for e in journal.recent_events())


def test_watcher_never_journals_secret_files(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    journal = Journal(tmp_path / "j.sqlite")
    watcher = ProjectWatcher(root, journal, debounce_s=0.2)
    watcher.start()
    try:
        (root / ".env").write_text("API_KEY=abc\n", encoding="utf-8")
        (root / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
        (root / "main.py").write_text("print(1)\n", encoding="utf-8")
        assert wait_for(lambda: any(e.path == "main.py" for e in journal.recent_events()))
    finally:
        watcher.stop()
    assert {e.path for e in journal.recent_events()} == {"main.py"}


def test_cli_watch_runs_for_a_bounded_time(tmp_path, capsys):
    root = tmp_path / "p"
    root.mkdir()
    assert cli.run_subcommand(["watch", "--project", str(root), "--seconds", "0.5"]) == 0
    assert (root / ".petru" / "journal.sqlite").is_file() and "Watching" in capsys.readouterr().out
