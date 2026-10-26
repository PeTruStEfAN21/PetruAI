"""`.petru/journal.sqlite`: file snapshots, change events with unified diffs, and the commit summary queue.
WAL mode and a busy timeout let the REPL and `petru watch` write at the same time."""

from __future__ import annotations

import difflib
import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from petru.index.chunker import iter_project_files

MAX_DIFF_CHARS = 20_000


@dataclass
class Event:
    id: int
    ts: float
    path: str
    kind: str  # created | modified | deleted
    diff: str


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def unified_diff(path: str, old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{path}", f"b/{path}", n=2
    )
    diff = "".join(lines)
    return diff if len(diff) <= MAX_DIFF_CHARS else diff[:MAX_DIFF_CHARS] + "\n[diff truncated]\n"


class Journal:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self.db.execute("pragma journal_mode=wal")
            self.db.execute("pragma busy_timeout=30000")
            self.db.executescript(
                """
                create table if not exists snapshots(path text primary key, sha1 text, content text);
                create table if not exists events(id integer primary key, ts real, path text, kind text,
                                                  diff text);
                create table if not exists commits(sha text primary key, ts real, status text, summary text);
                """
            )
            self.db.commit()

    def _snapshot(self, path: str) -> str | None:
        row = self.db.execute("select content from snapshots where path = ?", (path,)).fetchone()
        return row[0] if row else None

    def record_change(self, path: str, new_text: str | None) -> Event | None:
        """Diff `new_text` (None = deleted) against the last snapshot; None when nothing changed."""
        with self._lock:
            old = self._snapshot(path)
            if new_text is None:
                if old is None:
                    return None
                kind, diff = "deleted", unified_diff(path, old, "")
                self.db.execute("delete from snapshots where path = ?", (path,))
            else:
                if old == new_text:
                    return None
                kind = "created" if old is None else "modified"
                diff = unified_diff(path, old or "", new_text)
                self.db.execute(
                    "insert into snapshots(path, sha1, content) values (?, ?, ?) "
                    "on conflict(path) do update set sha1 = excluded.sha1, content = excluded.content",
                    (path, _sha1(new_text), new_text),
                )
            ts = time.time()
            cur = self.db.execute(
                "insert into events(ts, path, kind, diff) values (?, ?, ?, ?)", (ts, path, kind, diff)
            )
            self.db.commit()
            return Event(cur.lastrowid, ts, path, kind, diff)

    def snapshot_all(self, root: Path) -> int:
        """Record the current content of every project file without events, so first edits diff properly."""
        count = 0
        with self._lock:
            for file in iter_project_files(root):
                text = file.read_text(encoding="utf-8", errors="replace")
                rel = file.relative_to(root).as_posix()
                self.db.execute(
                    "insert into snapshots(path, sha1, content) values (?, ?, ?) "
                    "on conflict(path) do update set sha1 = excluded.sha1, content = excluded.content",
                    (rel, _sha1(text), text),
                )
                count += 1
            self.db.commit()
        return count

    def recent_events(self, since_ts: float = 0.0, limit: int = 200) -> list[Event]:
        with self._lock:
            rows = self.db.execute(
                "select id, ts, path, kind, diff from events where ts >= ? order by id limit ?",
                (since_ts, limit),
            ).fetchall()
        return [Event(*row) for row in rows]

    # -- commit summaries -----------------------------------------------------

    def enqueue_commit(self, sha: str) -> None:
        with self._lock:
            self.db.execute(
                "insert or ignore into commits(sha, ts, status) values (?, ?, 'pending')", (sha, time.time())
            )
            self.db.commit()

    def pending_commits(self, limit: int = 20) -> list[tuple[str, float]]:
        with self._lock:
            return self.db.execute(
                "select sha, ts from commits where status = 'pending' order by ts, rowid limit ?", (limit,)
            ).fetchall()

    def set_summary(self, sha: str, summary: str) -> None:
        with self._lock:
            self.db.execute("update commits set status = 'done', summary = ? where sha = ?", (summary, sha))
            self.db.commit()

    def recent_summaries(self, n: int = 5) -> list[tuple[str, str]]:
        with self._lock:
            rows = self.db.execute(
                "select sha, summary from commits where status = 'done' order by ts desc, rowid desc limit ?",
                (n,),
            ).fetchall()
        return [(sha, summary) for sha, summary in rows]

    def close(self) -> None:
        self.db.close()
