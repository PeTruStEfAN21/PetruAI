"""Watch a project folder and journal every save, whoever made it (VS Code, the agent, git checkout)."""

from __future__ import annotations

import threading
from pathlib import Path, PurePosixPath

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from petru.index.chunker import MAX_FILE_BYTES, is_secret_file
from petru.journal.store import Journal
from petru.tools.fs import IGNORED_DIRS

SKIP_DIRS = IGNORED_DIRS | {".petru"}


class ProjectWatcher(FileSystemEventHandler):
    def __init__(self, root: Path, journal: Journal, debounce_s: float = 1.0) -> None:
        self.root = root.resolve()
        self.journal = journal
        self.debounce_s = debounce_s
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._observer = Observer()

    def _relative(self, path: str) -> str | None:
        try:
            rel = Path(path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return None
        if any(part in SKIP_DIRS for part in PurePosixPath(rel).parts) or is_secret_file(rel):
            return None
        return rel

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        paths = [event.src_path, getattr(event, "dest_path", "") or ""]
        rels = [rel for rel in (self._relative(str(p)) for p in paths if p) if rel]
        if not rels:
            return
        with self._lock:
            self._pending.update(rels)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_s, self.flush)
            self._timer.daemon = True
            self._timer.start()

    def flush(self) -> None:
        with self._lock:
            pending, self._pending = sorted(self._pending), set()
        for rel in pending:
            path = self.root / rel
            if not path.exists():
                self.journal.record_change(rel, None)
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue  # still being written; the next event will catch it
            if len(data) > MAX_FILE_BYTES or b"\x00" in data[:8192]:
                continue
            self.journal.record_change(rel, data.decode("utf-8", errors="replace"))

    def start(self) -> None:
        self._observer.schedule(self, str(self.root), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
        self.flush()
