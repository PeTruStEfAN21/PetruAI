"""Embeddings from a local llama-server started with --embeddings (EmbeddingGemma 2)."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from typing import Literal

HttpPost = Callable[[str, dict, float], dict]
QUERY_PREFIX = "task: search result | query: "
DOCUMENT_PREFIX = "title: none | text: "
MAX_CHARS = 4000  # EmbeddingGemma reads 2,048 tokens; dense code is ~3 chars per token


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
        for i in range(0, len(texts), self.batch):
            inputs = [prefix + text[:MAX_CHARS] for text in texts[i : i + self.batch]]
            batch = self._request(inputs)
            if batch is None and len(inputs) > 1:  # one oversized text fails the whole batch: go one by one
                singles = [
                    self._request([text]) or self._request([text[: MAX_CHARS // 3]]) for text in inputs
                ]
                batch = None if any(v is None for v in singles) else [v[0] for v in singles]
            if batch is None:
                return None
            vectors.extend(batch)
        return vectors

    def _request(self, inputs: list[str]) -> list[list[float]] | None:
        try:
            data = self._post(self.url, {"input": inputs, "model": "embeddings"}, 120.0)["data"]
        except Exception:
            return None
        return [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]
