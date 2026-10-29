"""The full-screen view's top bar: what each switch shows and whether it can be clicked now."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from petru.app import App

BASE_TIERS = ("fast", "default", "quality")


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    enabled: bool


def _on(value: bool) -> str:
    return "on" if value else "off"


def toolbar_items(app: App) -> list[Item]:
    """Model and Team are greyed during a task: a server restart or new tools would break the work under way.
    Think and Yolo apply from the next request, so they stay clickable."""
    free = not app.in_task()
    return [
        Item("model", f"Model: {app.session.tier} ▾", free),
        Item("team", f"Team: {_on(app.team_on)}", free),
        Item("think", f"Think: {_on(app.thinking)}", True),
        Item("yolo", f"Yolo: {_on(app.session.yolo)}", True),
        Item("panel", "Panel", True),
    ]


def model_choices(cfg) -> list[str]:
    """The Model menu: the base tiers that exist, auto, then the fine-tuned ones."""
    tuned = sorted(tier for tier in cfg.tiers if tier.startswith("tuned"))
    return [*(tier for tier in BASE_TIERS if tier in cfg.tiers), "auto", *tuned]
