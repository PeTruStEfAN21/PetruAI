import pytest

from tracker import Tracker
from tracker.cli import main


@pytest.fixture
def db(tmp_path):
    return tmp_path / "cli.json"


@pytest.fixture
def run(db, capsys):
    def run(*args, actor="ana"):
        argv = ["--db", str(db)] + (["--as", actor] if actor else []) + [str(a) for a in args]
        code = main(argv)
        out, err = capsys.readouterr()
        return code, out.rstrip("\n"), err.rstrip("\n")

    return run


@pytest.fixture
def setup(run):
    assert run("user", "add", "ana", "Ana Pop", "--email", "ana@example.com", actor=None) == (0, "added user ana", "")
    assert run("user", "add", "bob", "Bob", actor=None)[1] == "added user bob"
    assert run("project", "add", "WEB", "Website")[1] == "added project WEB"
    return run


def test_user_and_project_lists(setup):
    assert setup("user", "list")[1] == "ana  Ana Pop <ana@example.com>\nbob  Bob"
    assert setup("project", "list")[1] == "WEB  Website"


def test_new_issue_and_show(setup, db):
    code, out, _ = setup("new", "WEB", "Login", "--priority", "high", "--label", "ui", "--label", "bug",
                         "--assignee", "bob", "--description", "Make it work")
    assert (code, out) == (0, "WEB-1")
    lines = setup("show", "WEB-1")[1].splitlines()
    assert lines == [
        "WEB-1 [open] (high) Login @bob #bug #ui",
        "reporter: ana",
        "depends on: -",
        "",
        "Make it work",
    ]
    assert Tracker(db).issue("WEB-1").reporter == "ana"


def test_errors_go_to_stderr_with_exit_code_1(setup):
    assert setup("new", "WEB", "Nobody", actor=None) == (1, "", "error: unknown user 'system'")
    assert setup("show", "WEB-9") == (1, "", "error: unknown issue 'WEB-9'")
    assert setup("user", "add", "ana", "Again")[2] == "error: user 'ana' already exists"


def test_usage_errors_exit_with_2(setup):
    with pytest.raises(SystemExit) as info:
        setup("report", "everything")
    assert info.value.code == 2


def test_assign_and_move(setup):
    setup("new", "WEB", "Task")
    assert setup("move", "WEB-1", "in_progress") == (1, "", "error: cannot start WEB-1: no assignee")
    assert setup("assign", "WEB-1", "bob")[1] == "WEB-1 assigned to bob"
    assert setup("move", "WEB-1", "in_progress")[1] == "WEB-1: open -> in_progress"
    assert setup("move", "WEB-1", "done")[2] == "error: cannot move WEB-1 from in_progress to done"
    assert setup("assign", "WEB-1", "none")[1] == "WEB-1 unassigned"


def test_labels_and_comments(setup):
    setup("new", "WEB", "Task")
    assert setup("label", "WEB-1", "ui")[1] == "WEB-1 labels: ui"
    assert setup("label", "WEB-1", "bug")[1] == "WEB-1 labels: bug, ui"
    assert setup("label", "WEB-1", "ui", "--remove")[1] == "WEB-1 labels: bug"
    assert setup("comment", "WEB-1", "Looks fine", actor="bob")[1] == "added comment #1 to WEB-1"
    assert setup("show", "WEB-1")[1].splitlines()[-2:] == ["", "#1 bob: Looks fine"]


def test_dependencies_and_order(setup):
    for title in ("Base", "Middle", "Top"):
        setup("new", "WEB", title)
    assert setup("depend", "WEB-3", "WEB-2")[1] == "WEB-3 depends on: WEB-2"
    assert setup("depend", "WEB-2", "WEB-1")[1] == "WEB-2 depends on: WEB-1"
    assert setup("depend", "WEB-1", "WEB-3")[2] == "error: dependency cycle: WEB-1 -> WEB-3 -> WEB-2 -> WEB-1"
    assert setup("order", "WEB")[1].splitlines() == [
        "1. WEB-1 [open] (medium) Base",
        "2. WEB-2 [open] (medium) Middle",
        "3. WEB-3 [open] (medium) Top",
    ]
    assert setup("depend", "WEB-3", "WEB-2", "--remove")[1] == "WEB-3 depends on: -"


def test_list_with_a_query(setup):
    setup("new", "WEB", "Login bug", "--label", "bug", "--priority", "urgent")
    setup("new", "WEB", "Docs", "--priority", "low")
    assert setup("list")[1].splitlines() == ["WEB-1 [open] (urgent) Login bug #bug", "WEB-2 [open] (low) Docs"]
    assert setup("list", "label:bug")[1] == "WEB-1 [open] (urgent) Login bug #bug"
    assert setup("list", "sort:priority", "is:open")[1].splitlines()[0].startswith("WEB-2")
    assert setup("list", "status:review")[1] == "no issues"
    assert setup("list", "(label:bug") == (1, "", "error: unbalanced parentheses")


def test_reports(setup):
    setup("new", "WEB", "One", "--assignee", "bob", "--label", "bug")
    setup("new", "WEB", "Two", "--label", "bug")
    setup("move", "WEB-2", "wontfix")
    lines = setup("report", "assignees")[1].splitlines()
    assert lines[0].split() == ["assignee", "open", "closed", "total"]
    assert set(lines[1]) == {"-", " "}
    assert [line.split() for line in lines[2:]] == [["bob", "1", "0", "1"], ["(unassigned)", "0", "1", "1"]]
    labels = setup("report", "labels", "--project", "WEB")[1].splitlines()
    assert labels[2].split() == ["bug", "1", "1", "2"]
    status = setup("report", "status")[1].splitlines()
    assert [line.split() for line in status[2:]] == [["open", "1"], ["in_progress", "0"], ["review", "0"], ["done", "0"], ["wontfix", "1"]]


def test_export(setup, tmp_path):
    setup("new", "WEB", "One", "--label", "bug")
    setup("new", "WEB", "Two")
    assert setup("export", "csv", "label:bug")[1].splitlines() == ["key,title,status,priority,assignee,labels", "WEB-1,One,open,2,,bug"]
    target = tmp_path / "out" / "issues.md"
    assert setup("export", "markdown", "--output", target)[1] == f"wrote 2 issues to {target}"
    assert target.read_text(encoding="utf-8").splitlines()[3] == "| WEB-2 | Two | open | medium | - | - |"


def test_log(setup):
    setup("new", "WEB", "Task")
    setup("label", "WEB-1", "ui", actor="bob")
    assert setup("log", "WEB-1")[1].splitlines() == ["4 ana create WEB-1 Task", "5 bob label WEB-1 +ui"]
    assert setup("log")[1].splitlines()[0] == "1 system user - ana"


def test_database_from_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRACKER_DB", str(tmp_path / "env.json"))
    assert main(["user", "add", "ana", "Ana"]) == 0
    assert Tracker(tmp_path / "env.json").user("ana").name == "Ana"
    capsys.readouterr()


def test_config_option(setup, tmp_path):
    config = tmp_path / "tracker.toml"
    config.write_text('[tracker]\ndefault_priority = "urgent"\n')
    assert setup("--config", config, "new", "WEB", "Hot")[1] == "WEB-1"
    assert setup("show", "WEB-1")[1].splitlines()[0] == "WEB-1 [open] (urgent) Hot"
    config.write_text("[tracker]\nwip_limit = -1\n")
    assert setup("--config", config, "list")[2] == "error: config key 'wip_limit' must be a positive integer"
