from __future__ import annotations

import json
import os
from pathlib import Path


class JsonStore:
    """One JSON document on disk, replaced atomically on every save."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.is_file():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
