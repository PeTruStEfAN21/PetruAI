"""Text shown by the command line for issues and audit entries."""

from ..models.entities import AuditEntry
from ..models.enums import priority_name
from ..models.issue import Issue


def format_line(issue: Issue) -> str:
    text = f"{issue.key} [{issue.status}] ({priority_name(issue.priority)}) {issue.title}"
    if issue.assignee:
        text += f" @{issue.assignee}"
    return text + "".join(f" #{label}" for label in issue.labels)


def format_detail(issue: Issue) -> str:
    lines = [
        format_line(issue),
        f"reporter: {issue.reporter}",
        f"depends on: {', '.join(issue.depends_on) or '-'}",
    ]
    if issue.description:
        lines += ["", issue.description]
    if issue.comments:
        lines.append("")
        lines += [f"#{c.id} {c.author}: {c.body}" for c in issue.comments]
    return "\n".join(lines)


def format_entry(entry: AuditEntry) -> str:
    return f"{entry.seq} {entry.actor} {entry.action} {entry.key or '-'} {entry.detail}"
