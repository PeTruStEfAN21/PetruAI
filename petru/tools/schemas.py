"""Export what the training pipeline (a separate Python environment) must mirror exactly: the tool schemas and
the BUILD-phase system prompt, so the model is trained on the same context it runs with.

    py -3.14 -m uv run python -m petru.tools.schemas    # training/schemas/tools.json + system_prompt.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from petru.agent.prompts import BASE_SYSTEM_PROMPT, BUILD_PHASE_PROMPT
from petru.tools.registry import default_registry

SCHEMAS_DIR = Path("training") / "schemas"


def dump_tool_schemas(path: Path) -> None:
    schemas = default_registry(ctx_online=False).schemas()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schemas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def build_phase_prompt() -> str:
    """The static part of the agent's system prompt while it edits code (BUILD phase)."""
    return f"{BASE_SYSTEM_PROMPT}\n\n{BUILD_PHASE_PROMPT}"


def dump_system_prompt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_phase_prompt(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else SCHEMAS_DIR / "tools.json"
    dump_tool_schemas(target)
    dump_system_prompt(target.parent / "system_prompt.txt")
