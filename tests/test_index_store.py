import math
import re
import sqlite3

from petru.index.embeddings import Embedder
from petru.index.store import CodeIndex

SYNONYMS = {"erase": "delete", "remove": "delete", "entry": "item", "record": "item"}


class FakeEmbedder:
    """Bag of words over a fixed vocabulary, with a few synonyms folded together."""

    def __init__(self) -> None:
        self.embedded = 0

    def embed(self, texts, kind):
        self.embedded += len(texts) if kind == "document" else 0
        vectors = []
        for text in texts:
            vec = [0.0] * 32
            for word in re.findall(r"[a-z]+", text.lower()):
                word = SYNONYMS.get(word, word)
                vec[hash(word) % 32] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


def make_project(root):
    (root / "src").mkdir(parents=True)
    (root / "src" / "config.py").write_text(
        "def parse_config(path):\n    return open(path).read()\n", encoding="utf-8"
    )
    (root / "src" / "items.py").write_text(
        'def delete_item(items, key):\n    """delete an item"""\n    items.pop(key)\n', encoding="utf-8"
    )
    (root / "src" / "users.py").write_text(
        "def add_user(users, name):\n    users.append(name)\n", encoding="utf-8"
    )
    return root


def test_bm25_finds_an_identifier(tmp_path):
    index = CodeIndex(tmp_path / "idx.sqlite", embedder=None)
    stats = index.update(make_project(tmp_path / "p"))
    assert stats["added"] == 3 and stats["chunks"] >= 3
    hits = index.search("parse_config")
    assert hits[0].path == "src/config.py" and hits[0].name == "parse_config" and hits[0].start == 1


def test_vector_search_finds_a_paraphrase(tmp_path):
    index = CodeIndex(tmp_path / "idx.sqlite", embedder=FakeEmbedder())
    index.update(make_project(tmp_path / "p"))
    hits = index.search("erase entry")
    assert hits and hits[0].name == "delete_item"


def test_fusion_ranks_a_chunk_found_by_both_first(tmp_path):
    index = CodeIndex(tmp_path / "idx.sqlite", embedder=FakeEmbedder())
    index.update(make_project(tmp_path / "p"))
    assert index.search("delete item")[0].name == "delete_item"


def test_index_update_removes_stale_chunks(tmp_path):
    project = make_project(tmp_path / "p")
    index = CodeIndex(tmp_path / "idx.sqlite", embedder=FakeEmbedder())
    index.update(project)
    (project / "src" / "config.py").rename(project / "src" / "settings.py")
    (project / "src" / "users.py").unlink()
    stats = index.update(project)
    assert stats["removed"] == 2 and stats["added"] == 1
    found = {h.path for h in index.search("parse_config add_user", limit=20)}
    assert "src/settings.py" in found and not found & {"src/config.py", "src/users.py"}
    db = sqlite3.connect(tmp_path / "idx.sqlite")
    chunk_ids = {row[0] for row in db.execute("select id from chunks")}
    fts_ids = {row[0] for row in db.execute("select rowid from chunks_fts")}
    assert fts_ids == chunk_ids
    assert index.stats()["embedded"] == len(chunk_ids)


def test_unchanged_files_are_not_embedded_again(tmp_path):
    embedder = FakeEmbedder()
    index = CodeIndex(tmp_path / "idx.sqlite", embedder=embedder)
    project = make_project(tmp_path / "p")
    index.update(project)
    first = embedder.embedded
    stats = index.update(project)
    assert (
        first >= 3
        and embedder.embedded == first
        and stats == {**stats, "added": 0, "updated": 0, "removed": 0}
    )


def test_embedder_failure_falls_back_to_bm25(tmp_path):
    class Down:
        def embed(self, texts, kind):
            return None

    index = CodeIndex(tmp_path / "idx.sqlite", embedder=Down())
    index.update(make_project(tmp_path / "p"))
    assert index.search("add_user")[0].name == "add_user" and index.stats()["embedded"] == 0


def test_query_with_fts_syntax_characters_is_safe(tmp_path):
    index = CodeIndex(tmp_path / "idx.sqlite", embedder=None)
    index.update(make_project(tmp_path / "p"))
    for query in ['"unbalanced', "a AND (b", "NEAR(x y)", "*", "", "-- ;"]:
        index.search(query)  # must not raise


def test_embedder_client_prefixes_batches_and_reports_failure():
    calls = []

    def post(url, payload, timeout):
        calls.append((url, payload))
        return {"data": [{"index": i, "embedding": [float(i), 1.0]} for i in range(len(payload["input"]))]}

    embedder = Embedder("http://127.0.0.1:8082/v1", http_post=post, batch=2)
    vectors = embedder.embed(["a", "b", "c"], "document")
    assert vectors == [[0.0, 1.0], [1.0, 1.0], [0.0, 1.0]] and len(calls) == 2
    assert calls[0][0] == "http://127.0.0.1:8082/v1/embeddings"
    assert calls[0][1]["input"][0] == "title: none | text: a"
    embedder.embed(["q"], "query")
    assert calls[-1][1]["input"] == ["task: search result | query: q"]

    def picky(url, payload, timeout):  # a batch with one oversized text fails as a whole
        if any("BIG" in text for text in payload["input"]) and len(payload["input"]) > 1:
            raise RuntimeError("500: input too large")
        return {"data": [{"index": i, "embedding": [1.0]} for i in range(len(payload["input"]))]}

    assert Embedder(http_post=picky, batch=4).embed(["a", "BIG", "c"], "document") == [[1.0], [1.0], [1.0]]

    def down(url, payload, timeout):
        raise OSError("refused")

    assert Embedder(http_post=down).embed(["a"], "document") is None
