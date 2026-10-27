"""Issues and their comments."""

import re
from dataclasses import dataclass, field

from ..errors import ValidationError
from .enums import CLOSED_STATUSES

ISSUE_KEY = re.compile(r"([A-Z][A-Z0-9]{1,9})-([1-9][0-9]*)")


@dataclass
class Comment:
    id: int
    author: str
    body: str
    created: int


@dataclass
class Issue:
    project: str
    number: int
    title: str
    reporter: str
    description: str = ""
    status: str = "open"
    priority: int = 2
    assignee: str | None = None
    labels: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    created: int = 0
    updated: int = 0

    @property
    def key(self) -> str:
        return f"{self.project}-{self.number}"

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    def sort_key(self) -> tuple[str, int]:
        return (self.project, self.number)


def parse_key(text: str) -> tuple[str, int]:
    match = ISSUE_KEY.fullmatch(text)
    if match is None:
        raise ValidationError(f"invalid issue key '{text}'")
    return match[1], int(match[2])


def key_order(key: str) -> tuple[str, int]:
    """Sort key for issue keys, so that WEB-2 comes before WEB-10."""
    project, _, number = key.rpartition("-")
    return project, int(number)
