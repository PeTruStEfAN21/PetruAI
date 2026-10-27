import json

import pytest

from tracker import StorageError, Tracker, TransitionError
from tracker.storage import SCHEMA_VERSION, migrate

V1 = {
    "version": 1,
    "users": {"ana": "Ana Pop", "bob": "Bob"},
    "projects": {"WEB": "Website", "OPS": "Ops"},
    "issues": [
        {"id": "WEB-1", "title": "Old bug", "state": "closed", "assignee": "ana",
         "tags": ["Bug", "ui"], "priority": "high", "reporter": "bob"},
        {"id": "WEB-4", "title": "Newer", "state": "open", "assignee": None,
         "tags": [], "priority": "low", "reporter": "ana", "blocked_by": ["WEB-1"]},
    ],
}


class Clock:
    def __init__(self):
        self.now = 50

    def __call__(self):
        self.now += 1
        return self.now


def populated(path):
    t = Tracker(path, clock=Clock())
    t.add_user("ana", "Ana", email="ana@example.com")
    t.add_project("WEB", "Website")
    t.create_issue("WEB", "First", reporter="ana", labels=["bug"], description="Text")
    t.create_issue("WEB", "Second", reporter="ana", assignee="ana", priority=4)
    t.add_dependency("WEB-2", "WEB-1")
    t.comment("WEB-1", "A note", by="ana")
    t.transition("WEB-2", "in_progress", by="ana")
    return t


def test_missing_file_is_an_empty_tracker(tmp_path):
    t = Tracker(tmp_path / "none.json")
    assert t.users() == [] and t.projects() == [] and t.issues() == [] and t.audit() == []
    assert not (tmp_path / "none.json").exists()


def test_round_trip(tmp_path):
    path = tmp_path / "nested" / "dir" / "data.json"
    first = populated(path)
    second = Tracker(path, clock=Clock())
    assert second.issues() == first.issues()
    assert second.users() == first.users()
    assert second.projects() == first.projects()
    assert second.audit() == first.audit()
    assert second.issue("WEB-1").comments[0].body == "A note"
    assert second.create_issue("WEB", "Third", reporter="ana").key == "WEB-3"


def test_file_layout(tmp_path):
    path = tmp_path / "data.json"
    populated(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert SCHEMA_VERSION == 2
    assert data["schema"] == 2
    assert set(data) == {"schema", "users", "projects", "counters", "issues", "audit"}
    assert data["counters"] == {"WEB": 2}
    assert [i["number"] for i in data["issues"]] == [1, 2]
    assert data["users"][0] == {"username": "ana", "name": "Ana", "email": "ana@example.com"}


def test_every_change_is_saved_without_temporary_files(tmp_path):
    path = tmp_path / "data.json"
    t = populated(path)
    t.add_label("WEB-2", "ui")
    assert Tracker(path).issue("WEB-2").labels == ["ui"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data.json"]


def test_failed_changes_do_not_touch_the_file(tmp_path):
    path = tmp_path / "data.json"
    t = populated(path)
    before = path.read_bytes()
    with pytest.raises(TransitionError):
        t.transition("WEB-1", "done")
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "content, message",
    [
        ("{not json", "corrupt data file"),
        ("[1, 2]", "corrupt data file"),
        ('{"schema": 3}', "unsupported schema 3"),
        ('{"users": []}', "unsupported schema None"),
        ('{"schema": 2, "users": [{"nick": "x"}], "projects": [], "issues": [], "counters": {}, "audit": []}',
         "corrupt data file"),
    ],
)
def test_bad_files(tmp_path, content, message):
    path = tmp_path / "data.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(StorageError, match=message):
        Tracker(path)


def test_migrate_v1():
    data = migrate(json.loads(json.dumps(V1)))
    assert data["schema"] == 2
    assert data["counters"] == {"OPS": 0, "WEB": 4}
    assert data["users"] == [
        {"username": "ana", "name": "Ana Pop", "email": None},
        {"username": "bob", "name": "Bob", "email": None},
    ]
    first, second = data["issues"]
    assert (first["project"], first["number"], first["status"]) == ("WEB", 1, "done")
    assert first["labels"] == ["bug", "ui"]
    assert first["priority"] == 3
    assert second["status"] == "open" and second["priority"] == 1
    assert second["depends_on"] == ["WEB-1"]
    assert data["audit"] == []


def test_migrate_leaves_current_schema_alone():
    current = {"schema": 2, "users": [], "projects": [], "issues": [], "counters": {}, "audit": []}
    assert migrate(current) == current


def test_tracker_loads_v1_and_saves_v2(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps(V1), encoding="utf-8")
    t = Tracker(path, clock=Clock())
    assert t.issue("WEB-1").status == "done"
    assert t.issue("WEB-4").depends_on == ["WEB-1"]
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
    assert t.create_issue("WEB", "After migration", reporter="bob").key == "WEB-5"
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == 2
    assert Tracker(path).issue("WEB-5").title == "After migration"
