import pytest

from tracker import (
    CLOSED_STATUSES,
    PRIORITY_NAMES,
    STATUSES,
    CycleError,
    DuplicateError,
    NotFoundError,
    QuerySyntaxError,
    StorageError,
    Tracker,
    TrackerError,
    TransitionError,
    ValidationError,
    parse_priority,
    priority_name,
)


class Clock:
    def __init__(self):
        self.now = 100

    def __call__(self):
        self.now += 1
        return self.now


@pytest.fixture
def tracker(tmp_path):
    t = Tracker(tmp_path / "data.json", clock=Clock())
    t.add_user("ana", "Ana Pop", email="ana@example.com")
    t.add_user("bob", "Bob Ionescu")
    t.add_project("WEB", "Website")
    return t


def test_error_hierarchy():
    for error in (NotFoundError, DuplicateError, ValidationError, TransitionError, CycleError, StorageError, QuerySyntaxError):
        assert issubclass(error, TrackerError)
    assert str(CycleError(["A-1", "A-2", "A-1"])) == "dependency cycle: A-1 -> A-2 -> A-1"
    assert QuerySyntaxError("bad", 4).position == 4


def test_statuses_and_priorities():
    assert STATUSES == ("open", "in_progress", "review", "done", "wontfix")
    assert CLOSED_STATUSES == {"done", "wontfix"}
    assert PRIORITY_NAMES == ("none", "low", "medium", "high", "urgent")
    assert parse_priority("high") == 3
    assert parse_priority("URGENT") == 4
    assert parse_priority("1") == 1
    assert parse_priority(0) == 0
    assert priority_name(2) == "medium"


@pytest.mark.parametrize("value, message", [(5, "priority must be between 0 and 4"), ("huge", "invalid priority 'huge'"), (-1, "between")])
def test_bad_priorities(value, message):
    with pytest.raises(ValidationError, match=message):
        parse_priority(value)


def test_users_are_sorted_and_unique(tracker):
    tracker.add_user("cara", "Cara")
    assert [u.username for u in tracker.users()] == ["ana", "bob", "cara"]
    assert tracker.user("ana").email == "ana@example.com"
    assert tracker.user("bob").email is None
    with pytest.raises(DuplicateError, match="user 'ana' already exists"):
        tracker.add_user("ana", "Again")
    with pytest.raises(NotFoundError, match="unknown user 'zed'"):
        tracker.user("zed")


@pytest.mark.parametrize("username", ["Ana", "a", "1abc", "ana-pop", "x" * 17])
def test_invalid_usernames(tracker, username):
    with pytest.raises(ValidationError, match="invalid username"):
        tracker.add_user(username, "Someone")


def test_invalid_email_and_empty_name(tracker):
    with pytest.raises(ValidationError, match="invalid email 'nope'"):
        tracker.add_user("dan", "Dan", email="nope")
    with pytest.raises(ValidationError, match="name must not be empty"):
        tracker.add_user("dan", "   ")


def test_projects(tracker):
    tracker.add_project("API2", "Backend")
    assert [p.key for p in tracker.projects()] == ["API2", "WEB"]
    assert tracker.project("WEB").name == "Website"
    with pytest.raises(DuplicateError, match="project 'WEB' already exists"):
        tracker.add_project("WEB", "Again")
    for key in ("web", "W", "WEB-1", "TOOLONGKEY1"):
        with pytest.raises(ValidationError, match="invalid project key"):
            tracker.add_project(key, "Bad")
    with pytest.raises(NotFoundError, match="unknown project 'NOPE'"):
        tracker.project("NOPE")


def test_create_issue_fills_every_field(tracker):
    issue = tracker.create_issue(
        "WEB", "  Login page  ", reporter="ana", description=" Build it ", priority="high", labels=["ui", "bug", "ui"], assignee="bob"
    )
    assert issue.key == "WEB-1"
    assert (issue.project, issue.number) == ("WEB", 1)
    assert issue.title == "Login page"
    assert issue.description == "Build it"
    assert issue.status == "open"
    assert issue.priority == 3
    assert issue.labels == ["bug", "ui"]
    assert issue.assignee == "bob"
    assert issue.reporter == "ana"
    assert issue.depends_on == [] and issue.comments == []
    assert issue.created == issue.updated > 100
    assert not issue.is_closed


def test_issue_numbers_are_per_project(tracker):
    tracker.add_project("API", "Backend")
    keys = [
        tracker.create_issue("WEB", "a", reporter="ana").key,
        tracker.create_issue("API", "b", reporter="ana").key,
        tracker.create_issue("WEB", "c", reporter="ana").key,
    ]
    assert keys == ["WEB-1", "API-1", "WEB-2"]
    assert [i.key for i in tracker.issues()] == ["API-1", "WEB-1", "WEB-2"]
    assert [i.key for i in tracker.issues("WEB")] == ["WEB-1", "WEB-2"]


def test_issues_sort_numerically(tracker):
    for n in range(11):
        tracker.create_issue("WEB", f"issue {n}", reporter="ana")
    assert [i.number for i in tracker.issues("WEB")] == list(range(1, 12))


def test_default_priority_is_medium(tracker):
    assert tracker.create_issue("WEB", "x", reporter="ana").priority == 2


@pytest.mark.parametrize(
    "kwargs, error, message",
    [
        ({"project": "NOPE"}, NotFoundError, "unknown project 'NOPE'"),
        ({"reporter": "zed"}, NotFoundError, "unknown user 'zed'"),
        ({"assignee": "zed"}, NotFoundError, "unknown user 'zed'"),
        ({"title": "   "}, ValidationError, "title must not be empty"),
        ({"title": "x" * 201}, ValidationError, "longer than 200"),
        ({"labels": ["Bad Label"]}, ValidationError, "invalid label 'Bad Label'"),
        ({"priority": 9}, ValidationError, "priority must be between 0 and 4"),
    ],
)
def test_create_issue_rejects_bad_input(tracker, kwargs, error, message):
    args = {"project": "WEB", "title": "Title", "reporter": "ana", **kwargs}
    with pytest.raises(error, match=message):
        tracker.create_issue(args.pop("project"), args.pop("title"), **args)
    assert tracker.issues() == []


def test_unknown_and_malformed_issue_keys(tracker):
    with pytest.raises(NotFoundError, match="unknown issue 'WEB-7'"):
        tracker.issue("WEB-7")
    with pytest.raises(ValidationError, match="invalid issue key 'web7'"):
        tracker.issue("web7")


def test_edit_title_and_description(tracker):
    tracker.create_issue("WEB", "Old", reporter="ana")
    issue = tracker.edit("WEB-1", title="New", description="Details", by="bob")
    assert (issue.title, issue.description) == ("New", "Details")
    assert tracker.audit("WEB-1")[-1].detail == "title,description"
    before = len(tracker.audit())
    tracker.edit("WEB-1", title="New")
    assert len(tracker.audit()) == before
