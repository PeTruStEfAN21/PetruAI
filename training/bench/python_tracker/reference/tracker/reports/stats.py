"""Open and closed counts grouped by assignee, label or status."""

from collections.abc import Iterable

from ..models.enums import STATUSES
from ..models.issue import Issue

UNASSIGNED = "(unassigned)"


def _bump(counts: dict, name: str, issue: Issue) -> None:
    bucket = counts.setdefault(name, {"open": 0, "closed": 0})
    bucket["closed" if issue.is_closed else "open"] += 1


def by_assignee(issues: Iterable[Issue]) -> dict[str, dict[str, int]]:
    """Sorted by username, with the unassigned issues last."""
    counts: dict = {}
    for issue in issues:
        _bump(counts, issue.assignee or UNASSIGNED, issue)
    names = sorted(n for n in counts if n != UNASSIGNED)
    if UNASSIGNED in counts:
        names.append(UNASSIGNED)
    return {name: counts[name] for name in names}


def by_label(issues: Iterable[Issue]) -> dict[str, dict[str, int]]:
    counts: dict = {}
    for issue in issues:
        for label in issue.labels:
            _bump(counts, label, issue)
    return {name: counts[name] for name in sorted(counts)}


def by_status(issues: Iterable[Issue]) -> dict[str, int]:
    counts = dict.fromkeys(STATUSES, 0)
    for issue in issues:
        counts[issue.status] += 1
    return counts


def report_rows(report: dict[str, dict[str, int]]) -> list[list]:
    return [[name, c["open"], c["closed"], c["open"] + c["closed"]] for name, c in report.items()]
