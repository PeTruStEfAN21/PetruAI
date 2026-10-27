"""Converts the in-memory state to and from the schema 2 JSON object."""

from dataclasses import asdict, dataclass, field

from ..errors import StorageError
from ..models.entities import AuditEntry, Project, User
from ..models.issue import Comment, Issue
from .migrations import SCHEMA_VERSION


@dataclass
class State:
    users: dict[str, User] = field(default_factory=dict)
    projects: dict[str, Project] = field(default_factory=dict)
    issues: dict[str, Issue] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    audit: list[AuditEntry] = field(default_factory=list)


def encode(state: State) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "users": [asdict(state.users[name]) for name in sorted(state.users)],
        "projects": [asdict(state.projects[key]) for key in sorted(state.projects)],
        "counters": dict(sorted(state.counters.items())),
        "issues": [asdict(issue) for issue in sorted(state.issues.values(), key=Issue.sort_key)],
        "audit": [asdict(entry) for entry in state.audit],
    }


def decode(data: dict) -> State:
    try:
        state = State()
        for raw in data["users"]:
            user = User(**raw)
            state.users[user.username] = user
        for raw in data["projects"]:
            project = Project(**raw)
            state.projects[project.key] = project
        for raw in data["issues"]:
            raw = dict(raw)
            raw["comments"] = [Comment(**c) for c in raw.get("comments", [])]
            issue = Issue(**raw)
            state.issues[issue.key] = issue
        state.counters = {key: int(value) for key, value in data["counters"].items()}
        state.audit = [AuditEntry(**raw) for raw in data["audit"]]
    except (KeyError, TypeError, ValueError, AttributeError):
        raise StorageError("corrupt data file") from None
    return state
