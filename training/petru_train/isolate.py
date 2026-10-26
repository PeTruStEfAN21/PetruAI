"""Run one heavy step in a fresh Python process.

Unsloth/transformers keep references to a loaded model after the call returns, so a second model load in
the same process finds the GPU still full. A child process gives every byte back to the driver when it
exits, and a CUDA crash in it cannot take the nightly orchestrator down.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

TRAINING_DIR = Path(__file__).resolve().parents[1]


def run_isolated(target: str, kwargs: dict[str, Any]) -> Any:
    """Call `module:function(**kwargs)` in a child process; kwargs and the result must be JSON-serializable.
    The child's output streams to this process's console so progress stays visible."""
    with tempfile.TemporaryDirectory(prefix="petru-isolate-") as tmp:
        args_file, out_file = Path(tmp) / "args.json", Path(tmp) / "out.json"
        args_file.write_text(json.dumps(kwargs), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "petru_train.isolate",
                target,
                str(args_file),
                str(out_file),
            ],
            cwd=str(TRAINING_DIR),
        )
        if proc.returncode != 0 or not out_file.is_file():
            raise RuntimeError(f"{target} failed in a subprocess (exit code {proc.returncode})")
        return json.loads(out_file.read_text(encoding="utf-8"))["result"]


def selftest(value: int, fail: bool = False) -> dict:
    """Used by the tests: proves the call crossed a process boundary."""
    if fail:
        raise ValueError("selftest asked to fail")
    return {"doubled": value * 2, "pid": os.getpid()}


def main(argv: list[str]) -> int:
    target, args_file, out_file = argv
    module_name, function_name = target.split(":")
    function = getattr(importlib.import_module(module_name), function_name)
    result = function(**json.loads(Path(args_file).read_text(encoding="utf-8")))
    Path(out_file).write_text(json.dumps({"result": result}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
