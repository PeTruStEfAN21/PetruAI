import pytest

from tracker import (
    Config,
    CycleError,
    DuplicateError,
    NotFoundError,
    Tracker,
    TransitionError,
    ValidationError,
    load_config,
    next_statuses,
)


class Clock:
    def __init__(self):
        self.now = 1000

    def __call__(self):
        self.now += 10
        return self.now


def make(tmp_path, config=None, issues=4):
    t = Tracker(tmp_path / "data.json", clock=Clock(), config=config)
    t.add_user("ana", "Ana")
    t.add_user("bob", "Bob")
    t.add_project("WEB", "Website")
    for n in range(1, issues + 1):
        t.create_issue("WEB", f"Task {n}", reporter="ana")
    return t


@pytest.fixture
def tracker(tmp_path):
    return make(tmp_path)


def test_next_statuses():
    assert next_statuses("open") == ["in_progress", "wontfix"]
    assert next_statuses("in_progress") == ["open", "review", "wontfix"]
    assert next_statuses("review") == ["in_progress", "done"]
    assert next_statuses("done") == ["open"]
    assert next_statuses("wontfix") == ["open"]
    with pytest.raises(ValidationError, match="unknown status 'later'"):
        next_statuses("later")


def test_full_happy_path(tracker):
    tracker.assign("WEB-1", "bob", by="ana")
    for status in ("in_progress", "review", "done"):
        issue = tracker.transition("WEB-1", status, by="bob")
    assert issue.status == "done" and issue.is_closed
    details = [e.detail for e in tracker.audit("WEB-1") if e.action == "status"]
    assert details == ["open -> in_progress", "in_progress -> review", "review -> done"]


def test_transition_errors(tracker):
    with pytest.raises(TransitionError, match="cannot move WEB-1 from open to done"):
        tracker.transition("WEB-1", "done")
    with pytest.raises(TransitionError, match="WEB-1 is already open"):
        tracker.transition("WEB-1", "open")
    with pytest.raises(TransitionError, match="cannot start WEB-1: no assignee"):
        tracker.transition("WEB-1", "in_progress")
    with pytest.raises(ValidationError, match="unknown status 'closed'"):
        tracker.transition("WEB-1", "closed")
    assert tracker.issue("WEB-1").status == "open"


def test_status_names_are_case_insensitive(tracker):
    assert tracker.transition("WEB-2", "WONTFIX").status == "wontfix"
    assert tracker.transition("WEB-2", "open").status == "open"


def test_transition_updates_timestamp(tracker):
    created = tracker.issue("WEB-1").created
    issue = tracker.transition("WEB-1", "wontfix")
    assert issue.updated > created
    assert issue.created == created


def test_done_requires_closed_dependencies(tracker):
    tracker.add_dependency("WEB-1", "WEB-2")
    tracker.add_dependency("WEB-1", "WEB-3")
    tracker.assign("WEB-1", "ana")
    tracker.transition("WEB-1", "in_progress")
    tracker.transition("WEB-1", "review")
    assert tracker.blockers("WEB-1") == ["WEB-2", "WEB-3"]
    with pytest.raises(TransitionError, match="WEB-1 is blocked by WEB-2, WEB-3"):
        tracker.transition("WEB-1", "done")
    tracker.transition("WEB-2", "wontfix")
    tracker.transition("WEB-3", "wontfix")
    assert tracker.blockers("WEB-1") == []
    assert tracker.transition("WEB-1", "done").status == "done"


def test_config_can_allow_blocked_done(tmp_path):
    t = make(tmp_path, Config(require_unblocked=False))
    t.add_dependency("WEB-1", "WEB-2")
    t.assign("WEB-1", "ana")
    for status in ("in_progress", "review", "done"):
        t.transition("WEB-1", status)
    assert t.issue("WEB-1").status == "done"


def test_wip_limit(tmp_path):
    t = make(tmp_path, Config(wip_limit=1))
    t.assign("WEB-1", "ana")
    t.assign("WEB-2", "ana")
    t.assign("WEB-3", "bob")
    t.transition("WEB-1", "in_progress")
    with pytest.raises(TransitionError, match="wip limit reached for ana"):
        t.transition("WEB-2", "in_progress")
    t.transition("WEB-3", "in_progress")
    t.transition("WEB-1", "review")
    assert t.transition("WEB-2", "in_progress").status == "in_progress"


def test_assign_and_unassign(tracker):
    tracker.assign("WEB-1", "ana", by="bob")
    tracker.assign("WEB-1", "ana", by="bob")
    tracker.assign("WEB-1", None, by="bob")
    assert tracker.issue("WEB-1").assignee is None
    assert [e.detail for e in tracker.audit("WEB-1") if e.action == "assign"] == ["ana", "none"]
    with pytest.raises(NotFoundError):
        tracker.assign("WEB-1", "zed")


def test_priority_and_labels(tracker):
    tracker.set_priority("WEB-1", "urgent", by="ana")
    tracker.add_label("WEB-1", "ui")
    tracker.add_label("WEB-1", "bug")
    tracker.add_label("WEB-1", "bug")
    assert tracker.issue("WEB-1").labels == ["bug", "ui"]
    tracker.remove_label("WEB-1", "ui")
    assert tracker.issue("WEB-1").labels == ["bug"]
    with pytest.raises(NotFoundError, match="WEB-1 has no label 'ui'"):
        tracker.remove_label("WEB-1", "ui")
    with pytest.raises(ValidationError):
        tracker.add_label("WEB-1", "No")
    entries = [(e.action, e.detail) for e in tracker.audit("WEB-1")][1:]
    assert entries == [("priority", "2 -> 4"), ("label", "+ui"), ("label", "+bug"), ("label", "-ui")]


def test_comments(tracker):
    first = tracker.comment("WEB-1", " Looks good ", by="bob")
    second = tracker.comment("WEB-1", "Thanks", by="ana")
    assert (first.id, first.author, first.body) == (1, "bob", "Looks good")
    assert second.id == 2
    assert [c.body for c in tracker.issue("WEB-1").comments] == ["Looks good", "Thanks"]
    with pytest.raises(ValidationError, match="comment must not be empty"):
        tracker.comment("WEB-1", "  ", by="bob")
    with pytest.raises(NotFoundError, match="unknown user 'zed'"):
        tracker.comment("WEB-1", "hi", by="zed")


def test_dependencies_are_sorted_and_unique(tracker):
    t = make(tracker.path.parent / "big", issues=12)
    t.add_dependency("WEB-1", "WEB-10")
    t.add_dependency("WEB-1", "WEB-2")
    assert t.issue("WEB-1").depends_on == ["WEB-2", "WEB-10"]
    assert t.dependents("WEB-2") == ["WEB-1"]
    with pytest.raises(DuplicateError, match="WEB-1 already depends on WEB-2"):
        t.add_dependency("WEB-1", "WEB-2")
    t.remove_dependency("WEB-1", "WEB-2")
    with pytest.raises(NotFoundError, match="WEB-1 does not depend on WEB-2"):
        t.remove_dependency("WEB-1", "WEB-2")
    with pytest.raises(NotFoundError, match="unknown issue 'WEB-99'"):
        t.add_dependency("WEB-1", "WEB-99")


def test_cycles_are_rejected_with_their_path(tracker):
    tracker.add_dependency("WEB-1", "WEB-2")
    tracker.add_dependency("WEB-2", "WEB-3")
    with pytest.raises(CycleError) as info:
        tracker.add_dependency("WEB-3", "WEB-1")
    assert info.value.path == ["WEB-3", "WEB-1", "WEB-2", "WEB-3"]
    assert str(info.value) == "dependency cycle: WEB-3 -> WEB-1 -> WEB-2 -> WEB-3"
    with pytest.raises(CycleError, match="WEB-4 -> WEB-4"):
        tracker.add_dependency("WEB-4", "WEB-4")
    assert tracker.issue("WEB-3").depends_on == []


def test_work_order(tracker):
    tracker.create_issue("WEB", "Task 5", reporter="ana")
    tracker.set_priority("WEB-4", 4)
    tracker.set_priority("WEB-5", 0)
    tracker.add_dependency("WEB-1", "WEB-3")
    tracker.add_dependency("WEB-3", "WEB-5")
    tracker.transition("WEB-2", "wontfix")
    order = [i.key for i in tracker.work_order("WEB")]
    assert order == ["WEB-4", "WEB-5", "WEB-3", "WEB-1"]


def test_closed_dependencies_do_not_hold_back_the_order(tracker):
    tracker.add_dependency("WEB-1", "WEB-2")
    tracker.transition("WEB-2", "wontfix")
    assert [i.key for i in tracker.work_order("WEB")] == ["WEB-1", "WEB-3", "WEB-4"]


def test_audit_log_records_actor_and_time(tracker):
    entries = tracker.audit()
    assert [e.seq for e in entries] == list(range(1, len(entries) + 1))
    assert [(e.action, e.key, e.detail) for e in entries[:3]] == [
        ("user", None, "ana"),
        ("user", None, "bob"),
        ("project", None, "WEB"),
    ]
    create = tracker.audit("WEB-2")[0]
    assert (create.action, create.actor, create.detail) == ("create", "ana", "Task 2")
    assert create.at == tracker.issue("WEB-2").created
    assert all(a.at < b.at for a, b in zip(entries, entries[1:]))


def test_load_config(tmp_path):
    assert load_config(tmp_path / "missing.toml") == Config()
    path = tmp_path / "tracker.toml"
    path.write_text('[tracker]\ndefault_priority = "high"\nwip_limit = 2\nrequire_unblocked = false\n')
    assert load_config(path) == Config(default_priority=3, wip_limit=2, require_unblocked=False)
    t = make(tmp_path, load_config(path), issues=1)
    assert t.issue("WEB-1").priority == 3


@pytest.mark.parametrize(
    "body, message",
    [
        ("[tracker]\ncolour = 1\n", "unknown config key 'colour'"),
        ("[tracker]\nwip_limit = 0\n", "must be a positive integer"),
        ("[tracker]\nrequire_unblocked = 1\n", "must be a boolean"),
        ("[tracker\n", "invalid config file"),
    ],
)
def test_bad_config(tmp_path, body, message):
    path = tmp_path / "tracker.toml"
    path.write_text(body)
    with pytest.raises(ValidationError, match=message):
        load_config(path)
