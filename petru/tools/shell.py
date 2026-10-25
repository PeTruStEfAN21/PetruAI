"""Run PowerShell commands inside the project: timeout, truncation, UTF-8, and danger classification."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Literal

from petru.tools.base import Tool, ToolContext, ToolResult

CommandKind = Literal["safe", "dangerous", "unknown"]

_DANGEROUS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\brm\s+-[a-z]*r",
        r"\bremove-item\b.*\s-r",
        r"\b(?:del|erase|rmdir|rd)\b.*\s/s\b",
        r"\bgit\s+push\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bgit\s+checkout\s+--\s",
        r"\bgit\s+clean\b",
        r"\bformat\s",
        r"\bshutdown\b",
        r"\b(?:stop|restart)-computer\b",
        r"\breg\s+(?:add|delete)\b",
        r">\s*\S*\.\.",
    )
]

_SAFE_PREFIXES = (
    "git status",
    "git diff",
    "git log",
    "git show",
    "git branch",
    "ls",
    "dir",
    "get-childitem",
    "cat",
    "get-content",
    "type",
    "pytest",
    "python -m pytest",
    "uv run pytest",
    "npm test",
    "npm run test",
    "npx vitest",
    "npx tsc",
    "npx eslint",
    "node --version",
    "python --version",
    "dart analyze",
    "flutter analyze",
    "flutter test",
    "dart test",
    "flutter --version",
    "where",
    "get-command",
)
_SAFE = [re.compile(rf"^{re.escape(p)}(?:\s|$)", re.IGNORECASE) for p in _SAFE_PREFIXES]
_COMPOUND = re.compile(r"[;|`]|&&|\|\||\$\(")

PS_PRELUDE = (
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $OutputEncoding=[System.Text.Encoding]::UTF8; "
)


def classify_command(cmd: str) -> CommandKind:
    text = cmd.strip()
    if any(rx.search(text) for rx in _DANGEROUS):
        return "dangerous"
    if _COMPOUND.search(text):
        return "unknown"
    if any(rx.match(text) for rx in _SAFE):
        return "safe"
    return "unknown"


def truncate_output(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return f"{text[:half]}\n... [truncated {len(text) - max_chars} chars] ...\n{text[-half:]}"


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=15)
    except OSError, subprocess.TimeoutExpired:
        proc.kill()


def run_shell(cmd: str, cwd: Path, timeout_s: int = 120, max_chars: int = 20000) -> ToolResult:
    argv = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        PS_PRELUDE + cmd,
    ]
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return ToolResult(f"Cannot start PowerShell: {exc}", True)
    try:
        raw, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            raw, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            raw = b""
        text = truncate_output(raw.decode("utf-8", errors="replace").replace("\r\n", "\n"), max_chars)
        return ToolResult(f"{text}\n[timed out after {timeout_s:g}s; process tree killed]".strip(), True)
    text = truncate_output(raw.decode("utf-8", errors="replace").replace("\r\n", "\n"), max_chars)
    return ToolResult(f"{text}\nexit code: {proc.returncode}".strip(), proc.returncode != 0)


class ShellTool(Tool):
    name = "shell"
    description = (
        "Run a PowerShell command in the project directory and return its output and exit code. "
        "Use it to run programs, install packages, and run tests."
    )
    mutating = True
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "PowerShell command line"},
            "timeout": {
                "type": "integer",
                "minimum": 1,
                "description": "Seconds before the command is killed (default 120)",
            },
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        return run_shell(str(args["command"]), ctx.project_root, timeout_s=int(args.get("timeout") or 120))


shell = ShellTool()
