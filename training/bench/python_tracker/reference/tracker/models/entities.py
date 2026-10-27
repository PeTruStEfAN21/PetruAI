"""Users, projects and audit entries."""

from dataclasses import dataclass


@dataclass
class User:
    username: str
    name: str
    email: str | None = None


@dataclass
class Project:
    key: str
    name: str


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    at: int
    actor: str
    action: str
    key: str | None
    detail: str
