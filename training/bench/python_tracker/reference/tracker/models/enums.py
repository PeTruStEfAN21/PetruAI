"""Statuses and priorities."""

from ..errors import ValidationError

STATUSES = ("open", "in_progress", "review", "done", "wontfix")
CLOSED_STATUSES = frozenset({"done", "wontfix"})
PRIORITY_NAMES = ("none", "low", "medium", "high", "urgent")
MIN_PRIORITY = 0
MAX_PRIORITY = len(PRIORITY_NAMES) - 1


def parse_status(value: str) -> str:
    status = str(value).strip().lower()
    if status not in STATUSES:
        raise ValidationError(f"unknown status '{value}'")
    return status


def parse_priority(value) -> int:
    """An int 0-4, or its name ("none" ... "urgent"), or the int as text."""
    if isinstance(value, bool):
        raise ValidationError(f"invalid priority '{value}'")
    if isinstance(value, int):
        number = value
    else:
        text = str(value).strip().lower()
        if text in PRIORITY_NAMES:
            return PRIORITY_NAMES.index(text)
        try:
            number = int(text)
        except ValueError:
            raise ValidationError(f"invalid priority '{value}'") from None
    if not MIN_PRIORITY <= number <= MAX_PRIORITY:
        raise ValidationError(f"priority must be between {MIN_PRIORITY} and {MAX_PRIORITY}")
    return number


def priority_name(value: int) -> str:
    return PRIORITY_NAMES[value]
