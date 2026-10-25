"""Session state: the IDLE -> DESIGN -> BUILD -> IDLE phase machine and the conversation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Phase(Enum):
    IDLE = "idle"
    DESIGN = "design"
    BUILD = "build"


@dataclass
class Plan:
    title: str
    steps: list[str]
    decisions: list[str] = field(default_factory=list)
    confirmed: bool = False


@dataclass
class Session:
    project_root: Path
    tier: str = "default"
    yolo: bool = False
    phase: Phase = Phase.IDLE
    messages: list[dict] = field(default_factory=list)
    plan: Plan | None = None
    always_allow: set[str] = field(default_factory=set)
    turn_tool_iterations: int = 0
    pending_decisions: list[str] = field(default_factory=list)

    def start_turn(self, text: str, quick: bool = False) -> None:
        """Record the user's prompt and arm the right phase for it."""
        self.messages.append({"role": "user", "content": text})
        self.turn_tool_iterations = 0
        if self.phase is Phase.IDLE:
            if quick or self.yolo:
                self.phase = Phase.BUILD
            else:
                self.phase = Phase.DESIGN
                self.pending_decisions = []
        elif self.phase is Phase.DESIGN and quick:
            self.phase = Phase.BUILD

    def confirm_plan(self) -> None:
        if self.plan is None:
            raise ValueError("no plan to confirm")
        self.plan.confirmed = True
        self.phase = Phase.BUILD

    def complete(self) -> None:
        self.phase = Phase.IDLE
        self.plan = None
        self.pending_decisions = []
