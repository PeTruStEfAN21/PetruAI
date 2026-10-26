"""Mine a git history into tool trajectories: read the file, edit or rewrite it, report done."""

from __future__ import annotations

import difflib
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from petru_train.filters import (
    has_secret,
    is_bump_message,
    is_env_file,
    is_generated_path,
    is_trivial_message,
    language_of,
)
from petru_train.samples import Sample, load_tools

TRAJECTORY_SYSTEM = (
    "You are Petru, a local coding agent working in the user's project through tools. Read the files you "
    "need, make the change with edit_file or write_file, then call task_complete with a short summary."
)
MAX_EDIT_LINES = 40
MAX_EDIT_BLOCKS = 6
MAX_CONTEXT_LINES = 3


@dataclass
class FileChange:
    path: str
    before: str | None
    after: str | None
    language: str | None


@dataclass
class Commit:
    sha: str
    message: str
    files: list[FileChange]
    date: str


def _git(repo: Path, *args: str) -> tuple[int, bytes]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return proc.returncode, proc.stdout


def _blob(repo: Path, rev: str, path: str) -> str | None:
    code, data = _git(repo, "show", f"{rev}:{path}")
    if code != 0 or b"\x00" in data:
        return None
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


def iter_commits(
    repo: Path, max_commits: int = 300, max_files: int = 3, max_file_chars: int = 6000
) -> Iterator[Commit]:
    """Newest first. Drops merges, trivial messages, deletions/renames, generated or binary-only changes,
    commits with more than `max_files` text files, oversized files, and anything that smells like a secret."""
    code, log = _git(repo, "log", "--no-merges", "--format=%H%x00%s%x00%cI", "-n", str(max_commits))
    if code != 0:
        return
    for line in log.decode("utf-8", errors="replace").splitlines():
        if line.count("\x00") != 2:
            continue
        sha, message, date = line.split("\x00")
        if is_trivial_message(message) or is_bump_message(message):
            continue
        _, status = _git(repo, "show", "--name-status", "--format=", sha)
        commit = _collect(
            repo, sha, message, date, status.decode("utf-8", errors="replace"), max_files, max_file_chars
        )
        if commit is not None:
            yield commit


def _collect(
    repo: Path, sha: str, message: str, date: str, status: str, max_files: int, max_file_chars: int
) -> Commit | None:
    changes: list[FileChange] = []
    for row in status.splitlines():
        parts = row.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        kind, path = parts[0][0], parts[-1]
        if kind in ("D", "R", "C"):
            return None  # no delete/rename tool: the trajectory could not be faithful
        if is_env_file(path):
            return None
        if is_generated_path(path):
            continue
        after = _blob(repo, sha, path)
        if after is None:
            continue
        before = _blob(repo, f"{sha}^", path) if kind != "A" else None
        if len(after) > max_file_chars or (before is not None and len(before) > max_file_chars):
            return None
        if has_secret(after) or (before is not None and has_secret(before)):
            return None
        changes.append(FileChange(path, before, after, language_of(path)))
        if len(changes) > max_files:
            return None
    if not changes:
        return None
    return Commit(sha, message, changes, date)


def derive_edits(before: str, after: str) -> list[tuple[str, str]] | None:
    """One (old, new) pair per changed block, in order, each `old` unique in the file as it is when that edit
    applies (context lines are added until it is), exactly how the agent's edit_file works. None when the
    change has too many or too large blocks, or a block cannot be made unique: then write_file is used."""
    b_lines = before.splitlines(keepends=True)
    a_lines = after.splitlines(keepends=True)
    ops = [op for op in difflib.SequenceMatcher(None, b_lines, a_lines, autojunk=False).get_opcodes()
           if op[0] != "equal"]  # fmt: skip
    if not ops or len(ops) > MAX_EDIT_BLOCKS:
        return None
    current, edits = before, []
    for _, i1, i2, j1, j2 in ops:
        if i2 - i1 > MAX_EDIT_LINES:
            return None
        chosen = None
        for context in range(0, MAX_CONTEXT_LINES + 1):
            lo, hi = max(0, i1 - context), min(len(b_lines), i2 + context)
            old = "".join(b_lines[lo:hi])
            if not old.strip():
                continue  # an insertion needs a neighbouring line as its anchor
            new = "".join(b_lines[lo:i1]) + "".join(a_lines[j1:j2]) + "".join(b_lines[i2:hi])
            if current.count(old) == 1:
                chosen = (old, new)
                break
        if chosen is None:
            return None
        current = current.replace(chosen[0], chosen[1], 1)
        edits.append(chosen)
    return edits if current == after else None


def read_result(text: str, limit: int = 400) -> str:
    """What the agent's read_file returns: numbered lines, 400 by default, then a continuation note."""
    lines = text.splitlines()
    out = [f"{i}\t{line}" for i, line in enumerate(lines[:limit], start=1)]
    if limit < len(lines):
        out.append(
            f"... {len(lines) - limit} more lines ({len(lines)} total). Use offset={limit + 1} to continue."
        )
    return "\n".join(out) if out else "(empty file)"


def _call(call_id: str, name: str, args: dict) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def commit_to_sample(commit: Commit, repo_name: str, license: str, tools: list[dict]) -> Sample:
    paths = ", ".join(f.path for f in commit.files)
    messages: list[dict] = [
        {"role": "system", "content": TRAJECTORY_SYSTEM},
        {"role": "user", "content": f"{commit.message}\n\nProject: {repo_name}. Files involved: {paths}."},
    ]
    for i, change in enumerate(commit.files, start=1):
        call_id = f"call_r{i}"
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [_call(call_id, "read_file", {"path": change.path})],
            }
        )
        content = (
            read_result(change.before)
            if change.before is not None
            else f"ERROR: File not found: {change.path}"
        )
        messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
    for i, change in enumerate(commit.files, start=1):
        after = change.after or ""
        edits = derive_edits(change.before, after) if change.before else None
        if edits:
            for k, (old, new) in enumerate(edits, start=1):
                call_id = f"call_w{i}_{k}"
                call = _call(call_id, "edit_file", {"path": change.path, "old": old, "new": new})
                messages.append({"role": "assistant", "content": "", "tool_calls": [call]})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": f"Edited {change.path}: replaced 1 occurrence",
                    }
                )
        else:
            call_id = f"call_w{i}"
            call = _call(call_id, "write_file", {"path": change.path, "content": after})
            result = f"Wrote {len(after.encode('utf-8'))} bytes to {change.path}"
            messages.append({"role": "assistant", "content": "", "tool_calls": [call]})
            messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
    messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [_call("call_done", "task_complete", {"summary": commit.message})],
        }
    )
    messages.append({"role": "tool", "tool_call_id": "call_done", "content": commit.message})
    languages = Counter(f.language for f in commit.files if f.language)
    language = languages.most_common(1)[0][0] if languages else "unknown"
    return Sample(
        id=f"{repo_name}:{commit.sha[:12]}",
        source="commit",
        repo=repo_name,
        license=license,
        commit=commit.sha,
        language=language,
        messages=messages,
        tools=tools,
    )


if __name__ == "__main__":
    repo_path = Path(sys.argv[1])
    limit = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 300
    samples = [
        commit_to_sample(c, repo_path.name, "local", load_tools()) for c in iter_commits(repo_path, limit)
    ]
    print(f"{len(samples)} samples from {repo_path}")
    if samples:
        print(samples[0].messages[1]["content"])
