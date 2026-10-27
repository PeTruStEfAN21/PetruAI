"""Shape checks for names, keys, labels and free text."""

import re

from .errors import ValidationError

USERNAME = re.compile(r"[a-z][a-z0-9_]{1,15}")
PROJECT_KEY = re.compile(r"[A-Z][A-Z0-9]{1,9}")
LABEL = re.compile(r"[a-z0-9][a-z0-9-]{0,29}")
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MAX_TITLE = 200


def validate_username(value: str) -> str:
    if not USERNAME.fullmatch(value):
        raise ValidationError(f"invalid username '{value}'")
    return value


def validate_project_key(value: str) -> str:
    if not PROJECT_KEY.fullmatch(value):
        raise ValidationError(f"invalid project key '{value}'")
    return value


def validate_label(value: str) -> str:
    if not LABEL.fullmatch(value):
        raise ValidationError(f"invalid label '{value}'")
    return value


def validate_email(value: str) -> str:
    if not EMAIL.fullmatch(value):
        raise ValidationError(f"invalid email '{value}'")
    return value


def validate_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise ValidationError("title must not be empty")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"title is longer than {MAX_TITLE} characters")
    return title


def require_text(value: str, what: str) -> str:
    text = value.strip()
    if not text:
        raise ValidationError(f"{what} must not be empty")
    return text
