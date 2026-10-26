"""The training pipeline reads the tool schemas from a committed JSON file; it must match the registry."""

import json
from pathlib import Path

from petru.tools.registry import default_registry
from petru.tools.schemas import dump_tool_schemas

COMMITTED = Path(__file__).resolve().parents[1] / "training" / "schemas" / "tools.json"


def test_dump_writes_registry_schemas(tmp_path):
    out = tmp_path / "tools.json"
    dump_tool_schemas(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == default_registry(ctx_online=False).schemas()
    assert [t["function"]["name"] for t in data][:3] == ["read_file", "write_file", "edit_file"]


def test_committed_schemas_are_in_sync(tmp_path):
    out = tmp_path / "tools.json"
    dump_tool_schemas(out)
    assert COMMITTED.is_file(), (
        "run: py -3.14 -m uv run python -m petru.tools.schemas training/schemas/tools.json"
    )
    assert out.read_text(encoding="utf-8") == COMMITTED.read_text(encoding="utf-8"), (
        "training/schemas/tools.json is stale; regenerate it with python -m petru.tools.schemas"
    )
