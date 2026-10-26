"""Embeddings from a local llama-server started with --embeddings (EmbeddingGemma 2)."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from typing import Literal

HttpPost = Callable[[str, dict, float], dict]
QUERY_PREFIX = "task: search result | query: "
DOCUMENT_PREFIX = "title: none | text: "
MAX_CHARS = 6000  # EmbeddingGemma reads 2,048 tokens; longer chunks are cut


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Embedder:
    def __init__(
        self, base_url: str = "http://127.0.0.1:8082/v1", http_post: HttpPost = _post_json, batch: int = 16
    ) -> None:
        self.url = base_url.rstrip("/") + "/embeddings"
        self._post = http_post
        self.batch = batch

    def embed(self, texts: list[str], kind: Literal["query", "document"]) -> list[list[float]] | None:
        """One vector per text, or None when the embeddings server is not available."""
        prefix = QUERY_PREFIX if kind == "query" else DOCUMENT_PREFIX
        vectors: list[list[float]] = []
        try:
            for i in range(0, len(texts), self.batch):
                inputs = [prefix + text[:MAX_CHARS] for text in texts[i : i + self.batch]]
                data = self._post(self.url, {"input": inputs, "model": "embeddings"}, 120.0)["data"]
                vectors.extend(item["embedding"] for item in sorted(data, key=lambda d: d["index"]))
        except Exception:
            return None
        return vectors
