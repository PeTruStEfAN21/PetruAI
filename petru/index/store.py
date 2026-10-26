"""The project code index: chunks in SQLite, BM25 via FTS5, vectors via sqlite-vec, fused by rank."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from petru.index.chunker import Chunk, chunk_file, iter_project_files

CANDIDATES = 30
RRF_K = 60
SNIPPET_LINES = 40


class SupportsEmbed(Protocol):
    def embed(self, texts: list[str], kind: str) -> list[list[float]] | None: ...


@dataclass
class Hit:
    path: str
    start: int
    end: int
    kind: str
    name: str
    snippet: str
    score: float


def fts_query(text: str) -> str:
    """Quote every word, OR them: user text can never be parsed as FTS5 syntax."""
    words = re.findall(r"\w+", text)
    return " OR ".join(f'"{w}"' for w in words[:32])


class CodeIndex:
    def __init__(self, db_path: Path, embedder: SupportsEmbed | None = None) -> None:
        self.db_path = db_path
        self.embedder = embedder
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, timeout=10)
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("pragma busy_timeout=5000")
        self._vec = self._load_vec()
        self.db.executescript(
            """
            create table if not exists files(path text primary key, sha1 text not null);
            create table if not exists chunks(id integer primary key, path text, start int, end int,
                                              kind text,
                                              name text, text text);
            create index if not exists chunks_path on chunks(path);
            create virtual table if not exists chunks_fts using fts5(text, name, path);
            create table if not exists meta(key text primary key, value text);
            """
        )

    def _load_vec(self) -> bool:
        try:
            import sqlite_vec

            self.db.enable_load_extension(True)
            sqlite_vec.load(self.db)
            self.db.enable_load_extension(False)
            return True
        except Exception:
            return False

    # -- vectors --------------------------------------------------------------

    def _dim(self) -> int | None:
        row = self.db.execute("select value from meta where key = 'dim'").fetchone()
        return int(row[0]) if row else None

    def _ensure_vec_table(self, dim: int) -> bool:
        if not self._vec:
            return False
        current = self._dim()
        if current is None:
            self.db.execute(
                f"create virtual table if not exists chunks_vec using vec0(embedding float[{dim}])"
            )
            self.db.execute("insert into meta(key, value) values ('dim', ?)", (str(dim),))
            return True
        return current == dim

    def _store_vectors(self, ids: list[int], texts: list[str]) -> None:
        if self.embedder is None or not ids:
            return
        vectors = self.embedder.embed(texts, "document")
        if not vectors or not self._ensure_vec_table(len(vectors[0])):
            return
        import sqlite_vec

        self.db.executemany(
            "insert into chunks_vec(rowid, embedding) values (?, ?)",
            [(cid, sqlite_vec.serialize_float32(vec)) for cid, vec in zip(ids, vectors, strict=True)],
        )

    # -- updates --------------------------------------------------------------

    def _remove(self, path: str) -> None:
        ids = [row[0] for row in self.db.execute("select id from chunks where path = ?", (path,))]
        if ids:
            marks = ",".join("?" * len(ids))
            self.db.execute(f"delete from chunks_fts where rowid in ({marks})", ids)
            if self._dim() is not None:
                self.db.execute(f"delete from chunks_vec where rowid in ({marks})", ids)
            self.db.execute("delete from chunks where path = ?", (path,))
        self.db.execute("delete from files where path = ?", (path,))

    def _add(self, path: str, sha1: str, chunks: list[Chunk]) -> None:
        ids = []
        for chunk in chunks:
            cur = self.db.execute(
                "insert into chunks(path, start, end, kind, name, text) values (?, ?, ?, ?, ?, ?)",
                (path, chunk.start, chunk.end, chunk.kind, chunk.name, chunk.text),
            )
            ids.append(cur.lastrowid)
            self.db.execute(
                "insert into chunks_fts(rowid, text, name, path) values (?, ?, ?, ?)",
                (cur.lastrowid, chunk.text, chunk.name, path),
            )
        self.db.execute("insert into files(path, sha1) values (?, ?)", (path, sha1))
        self._store_vectors(ids, [f"{path} {c.name}\n{c.text}" for c in chunks])

    def update(self, root: Path, prefix: str = "") -> dict:
        """Index `root` incrementally. With a prefix, paths are stored as `prefix/rel` and only that prefix's
        files are considered for removal, so several roots (SDK, docs) can share one index."""
        lead = f"{prefix}/" if prefix else ""
        known = dict(self.db.execute("select path, sha1 from files"))
        if prefix:
            known = {path: sha1 for path, sha1 in known.items() if path.startswith(lead)}
        seen: set[str] = set()
        stats = {"added": 0, "updated": 0, "removed": 0}
        for file in iter_project_files(root):
            rel = lead + file.relative_to(root).as_posix()
            seen.add(rel)
            data = file.read_bytes()
            sha1 = hashlib.sha1(data).hexdigest()
            if known.get(rel) == sha1:
                continue
            if rel in known:
                self._remove(rel)
                stats["updated"] += 1
            else:
                stats["added"] += 1
            self._add(rel, sha1, chunk_file(rel, data.decode("utf-8", errors="replace")))
        for rel in set(known) - seen:
            self._remove(rel)
            stats["removed"] += 1
        self.db.commit()
        stats["chunks"] = self.db.execute("select count(*) from chunks").fetchone()[0]
        return stats

    # -- search ---------------------------------------------------------------

    def _bm25(self, query: str) -> list[int]:
        match = fts_query(query)
        if not match:
            return []
        rows = self.db.execute(
            "select rowid from chunks_fts where chunks_fts match ? order by bm25(chunks_fts, 1.0, 5.0, 2.0) "
            "limit ?",
            (match, CANDIDATES),
        )
        return [row[0] for row in rows]

    def _vector(self, query: str) -> list[int]:
        if self.embedder is None or self._dim() is None:
            return []
        vectors = self.embedder.embed([query], "query")
        if not vectors:
            return []
        import sqlite_vec

        rows = self.db.execute(
            "select rowid from chunks_vec where embedding match ? and k = ? order by distance",
            (sqlite_vec.serialize_float32(vectors[0]), CANDIDATES),
        )
        return [row[0] for row in rows]

    def search(self, query: str, limit: int = 8) -> list[Hit]:
        scores: dict[int, float] = {}
        for ranking in (self._bm25(query), self._vector(query)):
            for rank, cid in enumerate(ranking):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        best = sorted(scores, key=lambda cid: -scores[cid])[:limit]
        hits = []
        for cid in best:
            row = self.db.execute(
                "select path, start, end, kind, name, text from chunks where id = ?", (cid,)
            )
            path, start, end, kind, name, text = row.fetchone()
            snippet = "\n".join(text.splitlines()[:SNIPPET_LINES])
            hits.append(Hit(path, start, end, kind, name, snippet, round(scores[cid], 5)))
        return hits

    def stats(self) -> dict:
        embedded = self.db.execute("select count(*) from chunks_vec").fetchone()[0] if self._dim() else 0
        return {
            "files": self.db.execute("select count(*) from files").fetchone()[0],
            "chunks": self.db.execute("select count(*) from chunks").fetchone()[0],
            "embedded": embedded,
            "vectors": self._vec,
        }

    def close(self) -> None:
        self.db.close()
