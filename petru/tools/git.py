"""Git inside the project, without a shell: status, diff, log, add, commit."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from petru.tools.base import Tool, ToolContext, ToolResult
from petru.tools.shell import truncate_output

ACTIONS = ("status", "diff", "log", "add", "commit")
DEFAULT_GITIGNORE = (
    "# Added by PetruAI before the first commit; edit freely.\n"
    "node_modules/\n.venv/\nvenv/\n__pycache__/\n*.pyc\n.pytest_cache/\n.ruff_cache/\n"
    ".dart_tool/\nbuild/\ndist/\n.env\n.env.*\n*.log\n"
    ".petru/index.sqlite*\n.petru/journal.sqlite*\n"
)


IGNORE_NOTE = "Created a default .gitignore (node_modules, .venv, build...)."


def ensure_gitignore(root: Path) -> bool:
    """Write a default .gitignore when the project has none; True when written."""
    path = root / ".gitignore"
    if path.exists():
        return False
    path.write_text(DEFAULT_GITIGNORE, encoding="utf-8", newline="\n")
    return True


def _run_git(args: list[str], cwd: Path, timeout_s: int = 120) -> ToolResult:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            timeout=timeout_s,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        return ToolResult("git is not installed or not on PATH", True)
    except subprocess.TimeoutExpired:
        return ToolResult(f"git {' '.join(args)} timed out after {timeout_s}s", True)
    out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n").strip()
    return ToolResult(out, proc.returncode != 0)


def _git_paths(args: list[str], root: Path) -> list[str]:
    """The NUL-separated paths a git command prints; empty when it fails (HEAD before the first commit)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        return []
    return [p for p in proc.stdout.decode("utf-8", errors="replace").split("\0") if p]


def unstage_ignored(root: Path) -> int:
    """Drop from the index the files .gitignore excludes that no commit contains yet (staged before the ignore
    file existed, e.g. node_modules); files committed earlier stay tracked. Returns how many were dropped."""
    ignored = _git_paths(["ls-files", "-z", "--cached", "--ignored", "--exclude-standard"], root)
    committed = set(_git_paths(["ls-tree", "-r", "-z", "--name-only", "HEAD"], root)) if ignored else set()
    fresh = [p for p in ignored if p not in committed]
    if fresh:
        subprocess.run(
            [
                "git",
                "--literal-pathspecs",
                "rm",
                "--cached",
                "-q",
                "--pathspec-from-file=-",
                "--pathspec-file-nul",
            ],
            cwd=str(root),
            input="\0".join(fresh).encode("utf-8"),
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    return len(fresh)


def tree_fingerprint(root: Path) -> str | None:
    """What a command could have changed in the working tree: status, staged and unstaged diffs, and the size
    and time of untracked files. None outside a git repository (then every command counts as a change)."""
    if not (root / ".git").exists():
        return None
    digest = hashlib.sha1()
    status = _run_git(["status", "--porcelain=v1", "-uall"], root).output
    digest.update(status.encode("utf-8", "replace"))
    for args in (["diff"], ["diff", "--cached"]):
        digest.update(_run_git(args, root).output.encode("utf-8", "replace"))
    for line in status.splitlines():
        if line.startswith("?? "):
            path = root / line[3:].strip().strip('"')
            if path.is_file():
                stat = path.stat()
                digest.update(f"{line}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def ensure_repo(root: Path) -> None:
    """Make `root` a git repository with a usable identity; a no-op when both already exist."""
    if not (root / ".git").is_dir():
        _run_git(["init", "-q"], root)
    if not _run_git(["config", "user.name"], root).output.strip():
        _run_git(["config", "user.name", "PetruAI"], root)
        _run_git(["config", "user.email", "petru@local"], root)


class GitTool(Tool):
    name = "git"
    description = (
        "Git in the project: status (short), diff, log (last 20), add (all by default), "
        "commit (stages everything, needs a message). Pushing is not available."
    )
    mutating = True
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "args": {"type": "array", "items": {"type": "string"}, "description": "Extra git arguments"},
            "message": {"type": "string", "description": "Commit message (commit only)"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    @classmethod
    def is_mutating(cls, args: dict) -> bool:
        return args.get("action") in ("add", "commit")

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        action = args.get("action")
        extra = [str(a) for a in (args.get("args") or [])]
        root = ctx.project_root
        if action == "status":
            r = _run_git(["status", "--short", *extra], root)
            return r if r.is_error else ToolResult(r.output or "(clean)")
        if action == "diff":
            r = _run_git(["diff", *extra], root)
            return r if r.is_error else ToolResult(truncate_output(r.output, 20000) or "(no changes)")
        if action == "log":
            r = _run_git(["log", "--oneline", "-n", "20", *extra], root)
            if r.is_error and "does not have any commits" in r.output:
                return ToolResult("(no commits yet)")
            return r
        if action == "add":
            wrote_ignore = ensure_gitignore(root)  # before staging, or node_modules lands in the index
            if wrote_ignore:
                unstage_ignored(root)
            r = _run_git(["add", *(extra or ["-A"])], root)
            if r.is_error:
                return r
            return ToolResult((IGNORE_NOTE + "\n" if wrote_ignore else "") + "Staged.")
        if action == "commit":
            message = args.get("message")
            if not message:
                return ToolResult("commit requires a non-empty message", True)
            ensure_repo(root)
            wrote_ignore = ensure_gitignore(root)
            if wrote_ignore:
                unstage_ignored(
                    root
                )  # staged earlier (e.g. by a shell command) before the ignore file existed
            staged = _run_git(["add", "-A"], root)
            if staged.is_error:
                return staged
            committed = _run_git(["commit", "-m", str(message), *extra], root)
            committed.output = truncate_output(committed.output, 3000)  # one line per new file otherwise
            if wrote_ignore and not committed.is_error:
                committed.output = IGNORE_NOTE + "\n" + committed.output
            return committed
        return ToolResult(f"Unknown git action {action!r}. Allowed: {', '.join(ACTIONS)}.", True)


git = GitTool()
