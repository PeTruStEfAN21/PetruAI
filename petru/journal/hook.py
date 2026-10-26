"""A git post-commit hook that queues each commit for a summary. It runs in the background and always exits 0:
a missing Python, uv or PetruAI checkout must never block or fail the user's commit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from petru.journal.store import Journal

HOOK_MARK = "# petru-journal-hook"
USER_HOOK = "post-commit.user"


def hook_script(repo_root: Path) -> str:
    root = repo_root.as_posix()
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARK}: queue this commit for a summary; never blocks or fails the commit\n"
        f'if [ -x "$(dirname "$0")/{USER_HOOK}" ]; then "$(dirname "$0")/{USER_HOOK}" "$@" || true; fi\n'
        f'( py -3.14 -m uv run --project "{root}" python -m petru.journal.hook enqueue "$PWD" '
        ">/dev/null 2>&1 || true ) &\n"
        "exit 0\n"
    )


def _hooks_dir(project: Path) -> Path:
    return project / ".git" / "hooks"


def install_hook(project: Path, repo_root: Path) -> Path:
    hooks = _hooks_dir(project)
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "post-commit"
    if hook.is_file() and HOOK_MARK not in hook.read_text(encoding="utf-8", errors="replace"):
        hook.replace(hooks / USER_HOOK)  # keep the user's own hook; ours calls it first
    hook.write_text(hook_script(repo_root), encoding="utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    return hook


def uninstall_hook(project: Path) -> None:
    hooks = _hooks_dir(project)
    hook = hooks / "post-commit"
    if hook.is_file() and HOOK_MARK in hook.read_text(encoding="utf-8", errors="replace"):
        hook.unlink()
    user = hooks / USER_HOOK
    if user.is_file() and not hook.exists():
        user.replace(hook)


def enqueue(project: Path, sha: str | None = None) -> str | None:
    if sha is None:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(project), capture_output=True, text=True, encoding="utf-8"
        )
        sha = proc.stdout.strip() if proc.returncode == 0 else None
    if not sha:
        return None
    journal = Journal(project / ".petru" / "journal.sqlite")
    try:
        journal.enqueue_commit(sha)
    finally:
        journal.close()
    return sha


def main(argv: list[str]) -> int:
    try:
        if len(argv) >= 2 and argv[0] == "enqueue":
            enqueue(Path(argv[1]))
    except Exception:
        pass  # a hook must never fail the commit
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
