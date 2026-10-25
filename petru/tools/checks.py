"""Detect and run the project's test and analysis commands."""

from __future__ import annotations

import json
from pathlib import Path

from petru.tools.base import Tool, ToolContext, ToolResult
from petru.tools.shell import run_shell

CHECK_TIMEOUT_S = 600


def _has_python_tests(root: Path) -> bool:
    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file():
        return True
    tests = root / "tests"
    return tests.is_dir() and any(tests.rglob("*.py"))


def detect_checks(root: Path) -> list[str]:
    commands: list[str] = []
    if _has_python_tests(root):
        commands.append("uv run pytest -q" if (root / "uv.lock").is_file() else "python -m pytest -q")
    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
        except json.JSONDecodeError, OSError, AttributeError:
            scripts = {}
        if "test" in scripts:
            commands.append("npm test --silent")
    if (root / "tsconfig.json").is_file():
        commands.append("npx tsc --noEmit -p .")
    pubspec = root / "pubspec.yaml"
    if pubspec.is_file():
        text = pubspec.read_text(encoding="utf-8", errors="replace")
        commands.append("dart analyze")
        commands.append("flutter test" if "sdk: flutter" in text else "dart test")
    return commands


class RunChecksTool(Tool):
    name = "run_checks"
    description = (
        "Detect and run the project's checks (pytest, npm test, tsc, dart analyze, flutter test) "
        "and report PASS/FAIL per command. Run it after every change."
    )
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        commands = detect_checks(ctx.project_root)
        if not commands:
            return ToolResult(
                "No checks detected: no pyproject.toml, pytest.ini or tests/*.py, "
                "no package.json test script, no tsconfig.json, no pubspec.yaml."
            )
        reports, failed = [], False
        for cmd in commands:
            result = run_shell(cmd, ctx.project_root, timeout_s=CHECK_TIMEOUT_S)
            tail = "\n".join(result.output.splitlines()[-40:])
            reports.append(f"[{'FAIL' if result.is_error else 'PASS'}] {cmd}\n{tail}")
            failed = failed or result.is_error
        return ToolResult("\n\n".join(reports), failed)


run_checks = RunChecksTool()
