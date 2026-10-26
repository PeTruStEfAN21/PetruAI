"""Export the tool schemas as JSON for the training pipeline (a separate Python environment)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from petru.tools.registry import default_registry


def dump_tool_schemas(path: Path) -> None:
    schemas = default_registry(ctx_online=False).schemas()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schemas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    dump_tool_schemas(Path(sys.argv[1] if len(sys.argv) > 1 else "training/schemas/tools.json"))
