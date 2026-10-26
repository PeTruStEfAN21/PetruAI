"""Slash commands typed at the petru prompt."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    arg: str


HELP_TEXT = """\
Type a request to start a task: Petru asks design questions, proposes a plan, then builds after you confirm.

Commands:
  /help            this help
  /model [tier]    show or switch the model tier (default, quality, fast); restarts the server
  /plan            show the current plan
  /quick <text>    skip the design questions and build right away (small fixes)
  /done            end the current task and go back to idle
  /yolo            toggle yolo mode (no confirmations, build immediately)
  /status          phase, tier, project, online/offline
  /exit            quit (Ctrl+D also works)
"""


def parse_command(line: str) -> Command | None:
    """A Command for `/name [arg]` lines; None for ordinary prompts."""
    text = line.strip()
    if not text.startswith("/"):
        return None
    head, _, rest = text[1:].partition(" ")
    return Command(head.strip().lower(), rest.strip())
