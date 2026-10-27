"""CSV export."""

import csv
import io
from collections.abc import Iterable

from ..models.issue import Issue

COLUMNS = ["key", "title", "status", "priority", "assignee", "labels"]


def to_csv(issues: Iterable[Issue]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for issue in issues:
        writer.writerow(
            [issue.key, issue.title, issue.status, issue.priority, issue.assignee or "", ";".join(issue.labels)]
        )
    return buffer.getvalue()
