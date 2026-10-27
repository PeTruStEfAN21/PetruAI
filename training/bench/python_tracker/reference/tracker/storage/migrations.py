"""Schema versions of the data file and the upgrade from version 1."""

from ..errors import StorageError
from ..models.enums import PRIORITY_NAMES

SCHEMA_VERSION = 2


def schema_of(data: dict):
    if "schema" in data:
        return data["schema"]
    return data.get("version")


def migrate(data: dict) -> dict:
    """Returns the data in the current schema; unknown versions raise StorageError."""
    version = schema_of(data)
    if version == SCHEMA_VERSION:
        return data
    if version == 1:
        return _v1_to_v2(data)
    raise StorageError(f"unsupported schema {version}")


def _v1_to_v2(data: dict) -> dict:
    try:
        users = [
            {"username": name, "name": full, "email": None}
            for name, full in sorted(data.get("users", {}).items())
        ]
        projects = [{"key": key, "name": name} for key, name in sorted(data.get("projects", {}).items())]
        counters = {p["key"]: 0 for p in projects}
        issues = []
        for old in data.get("issues", []):
            project, _, number = old["id"].rpartition("-")
            number = int(number)
            counters[project] = max(counters.get(project, 0), number)
            issues.append(
                {
                    "project": project,
                    "number": number,
                    "title": old["title"],
                    "reporter": old.get("reporter", "system"),
                    "description": "",
                    "status": "done" if old.get("state") == "closed" else "open",
                    "priority": PRIORITY_NAMES.index(old.get("priority", "medium")),
                    "assignee": old.get("assignee"),
                    "labels": sorted({tag.lower() for tag in old.get("tags", [])}),
                    "depends_on": list(old.get("blocked_by", [])),
                    "comments": [],
                    "created": 0,
                    "updated": 0,
                }
            )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise StorageError("corrupt data file") from None
    return {
        "schema": SCHEMA_VERSION,
        "users": users,
        "projects": projects,
        "counters": counters,
        "issues": issues,
        "audit": [],
    }
