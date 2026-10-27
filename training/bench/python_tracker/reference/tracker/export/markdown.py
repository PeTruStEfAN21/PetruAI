"""Markdown table export."""

from collections.abc import Iterable

from ..models.enums import priority_name
from ..models.issue import Issue

HEADER = "| Key | Title | Status | Priority | Assignee | Labels |"
RULE = "|---|---|---|---|---|---|"


def _cell(text: str) -> str:
    return text.replace("|", "\\|") or "-"


def to_markdown(issues: Iterable[Issue]) -> str:
    lines = [HEADER, RULE]
    for issue in issues:
        cells = [
            issue.key,
            issue.title,
            issue.status,
            priority_name(issue.priority),
            issue.assignee or "",
            ", ".join(issue.labels),
        ]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return "\n".join(lines) + "\n"
