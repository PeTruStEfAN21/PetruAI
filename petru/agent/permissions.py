"""Who may do what, and when: phase gating plus confirmation rules for risky actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from petru.agent.state import Phase, Session
from petru.tools.base import Tool
from petru.tools.paths import OutsideProjectError, resolve_in_project
from petru.tools.shell import classify_command

DESIGN_ALLOWED = {
    "read_file", "list_dir", "glob", "grep", "ask_user", "plan",
    "remember", "recall", "search_code", "search_docs",  # memory and search never touch the project's code
    "choose_mode",  # a team's lead chooses how to work before it plans
}  # fmt: skip


@dataclass
class Decision:
    kind: Literal["allow", "ask", "deny"]
    reason: str


def decide(tool: Tool, args: dict, session: Session) -> Decision:
    if session.phase is Phase.DESIGN and tool.name not in DESIGN_ALLOWED:
        return Decision("deny", f"{tool.name} is not allowed before the plan is confirmed")
    if session.yolo:
        return Decision("allow", "yolo mode")
    if tool.name == "shell":
        kind = classify_command(str(args.get("command", "")))
        if kind == "dangerous":
            return Decision("ask", "dangerous command")
        if kind == "safe":
            return Decision("allow", "safe command")
        if tool.name in session.always_allow:
            return Decision("allow", "always allowed by the user")
        return Decision("ask", "unknown command")
    if tool.name in session.always_allow:
        return Decision("allow", "always allowed by the user")
    if tool.mutating and args.get("path") is not None:
        try:
            resolve_in_project(str(args["path"]), session.project_root)
        except OutsideProjectError:
            return Decision("ask", "path is outside the project")
    return Decision("allow", "")
