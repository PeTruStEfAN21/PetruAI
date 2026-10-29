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
  /model [tier]    show or switch the model tier (default, quality, fast, auto); restarts the server
  /plan            show the current plan
  /quick <text>    skip the design questions and build right away (small fixes)
  /done            end the current task and go back to idle
  /yolo            toggle yolo mode (no confirmations, build immediately)
  /status          phase, tier, project, online/offline
  /details         context used, replies and speed, tool calls, why the last turn stopped, team state
  /team            switch team mode on or off between tasks (the 35B leads, the 4B takes simple pieces)
  /think           show the model's reasoning before it answers (slower; the reasoning is not kept)
  /memory          what Petru remembers (global and project memory)
  /journal         recent commit summaries and pending ones
  /exit            quit (Ctrl+D also works)

Full screen (petru --plain keeps the line mode):
  Esc              stop what the agent is doing now; the session stays open
  F2               hide or show the side panel (it hides itself on narrow terminals)
  PageUp/PageDown  scroll the conversation (the mouse wheel too)
  click            the top bar switches model, team, think and yolo; a choice answers a question
  Shift+drag       select text to copy (the mouse belongs to the app otherwise)
  Typing while the agent works sends the message to it at its next step.
"""


def parse_command(line: str) -> Command | None:
    """A Command for `/name [arg]` lines; None for ordinary prompts."""
    text = line.strip()
    if not text.startswith("/"):
        return None
    head, _, rest = text[1:].partition(" ")
    return Command(head.strip().lower(), rest.strip())
