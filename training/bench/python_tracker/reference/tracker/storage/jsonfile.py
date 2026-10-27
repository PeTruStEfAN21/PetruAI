"""Reading and atomically writing the JSON data file."""

import json
import os
import tempfile
from pathlib import Path

from ..errors import StorageError


def read_json(path) -> dict | None:
    """The parsed object, or None when the file does not exist."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise StorageError("corrupt data file") from None
    if not isinstance(data, dict):
        raise StorageError("corrupt data file")
    return data


def write_json_atomic(path, data: dict) -> None:
    """Writes to a temporary file next to `path`, then renames it over the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
