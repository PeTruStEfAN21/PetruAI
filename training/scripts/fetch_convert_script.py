"""Fetch llama.cpp convert_hf_to_gguf.py and its packages at the pinned tag into infra/llama.cpp/convert/.

Run once, online: `py -3.14 training/scripts/fetch_convert_script.py`. The target folder is gitignored.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

TAG = "b11877"
RAW = f"https://raw.githubusercontent.com/ggml-org/llama.cpp/{TAG}/"
API = f"https://api.github.com/repos/ggml-org/llama.cpp/contents/{{path}}?ref={TAG}"
TOP_FILES = ["convert_hf_to_gguf.py", "gguf-py/pyproject.toml"]
DIRS = ["gguf-py/gguf", "conversion"]  # the converter is a package beside the script since 2026
SKIP_DIRS = {"scripts", "tests"}
DEST = Path(__file__).resolve().parents[2] / "infra" / "llama.cpp" / "convert"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def list_files(path: str) -> list[str]:
    files: list[str] = []
    for entry in json.loads(fetch(API.format(path=path))):
        if entry["type"] == "dir" and entry["name"] not in SKIP_DIRS:
            files.extend(list_files(f"{path}/{entry['name']}"))
        elif entry["type"] == "file" and entry["name"].endswith((".py", ".toml", ".json", ".txt")):
            files.append(f"{path}/{entry['name']}")
    return files


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    files = list(TOP_FILES)
    for directory in DIRS:
        files.extend(list_files(directory))
    for rel in files:
        target = DEST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fetch(RAW + rel))
        print(f"fetched {rel} ({target.stat().st_size} bytes)")
    (DEST / "VERSION").write_text(f"llama.cpp {TAG}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
