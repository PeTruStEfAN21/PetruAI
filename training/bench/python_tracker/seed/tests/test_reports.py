import csv
import io

import pytest

from tracker import Tracker
from tracker.export import to_csv, to_markdown
from tracker.reports import by_assignee, by_label, by_status, render_table


@pytest.fixture
def tracker(tmp_path):
    t = Tracker(tmp_path / "data.json")
    t.add_user("ana", "Ana")
    t.add_user("bob", "Bob")
    t.add_project("WEB", "Website")
    t.create_issue("WEB", "Login | signup", reporter="ana", priority=3, labels=["bug", "ui"], assignee="bob")
    t.create_issue("WEB", "Docs", reporter="ana", priority=1, labels=["docs"], assignee="ana")
    t.create_issue("WEB", 'Say "hi", world', reporter="ana", labels=["bug"])
    t.create_issue("WEB", "Old", reporter="ana", assignee="bob")
    t.transition("WEB-4", "wontfix")
    t.assign("WEB-3", "ana")
    t.transition("WEB-3", "in_progress")
    t.transition("WEB-3", "review")
    t.transition("WEB-3", "done")
    t.assign("WEB-3", None)
    return t


def test_by_assignee_puts_unassigned_last(tracker):
    assert list(by_assignee(tracker.issues()).items()) == [
        ("ana", {"open": 1, "closed": 0}),
        ("bob", {"open": 1, "closed": 1}),
        ("(unassigned)", {"open": 0, "closed": 1}),
    ]


def test_by_label(tracker):
    assert list(by_label(tracker.issues()).items()) == [
        ("bug", {"open": 1, "closed": 1}),
        ("docs", {"open": 1, "closed": 0}),
        ("ui", {"open": 1, "closed": 0}),
    ]


def test_by_status_lists_every_status(tracker):
    assert by_status(tracker.issues()) == {"open": 2, "in_progress": 0, "review": 0, "done": 1, "wontfix": 1}
    assert list(by_status([])) == ["open", "in_progress", "review", "done", "wontfix"]


def test_render_table():
    text = render_table(["name", "open", "notes"], [["ana", 3, "x"], ["bartholomew", 12, ""]])
    assert text == (
        "name         open  notes\n"
        "-----------  ----  -----\n"
        "ana             3  x\n"
        "bartholomew    12"
    )


def test_render_table_without_rows():
    assert render_table(["a", "bb"], []) == "a  bb\n-  --"


def test_csv_export(tracker):
    text = to_csv(tracker.issues())
    assert text.splitlines()[0] == "key,title,status,priority,assignee,labels"
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[1] == ["WEB-1", "Login | signup", "open", "3", "bob", "bug;ui"]
    assert rows[3] == ["WEB-3", 'Say "hi", world', "done", "2", "", "bug"]
    assert len(rows) == 5
    assert text.endswith("\n") and "\r" not in text


def test_csv_export_of_nothing():
    assert to_csv([]) == "key,title,status,priority,assignee,labels\n"


def test_markdown_export(tracker):
    lines = to_markdown(tracker.issues()[:2]).splitlines()
    assert lines == [
        "| Key | Title | Status | Priority | Assignee | Labels |",
        "|---|---|---|---|---|---|",
        "| WEB-1 | Login \\| signup | open | high | bob | bug, ui |",
        "| WEB-2 | Docs | open | low | ana | docs |",
    ]


def test_markdown_empty_cells(tracker):
    line = to_markdown([tracker.issue("WEB-4")]).splitlines()[2]
    assert line == "| WEB-4 | Old | wontfix | medium | bob | - |"
    assert to_markdown([]).endswith("|---|---|---|---|---|---|\n")
