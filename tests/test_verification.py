"""task_complete needs a green run_checks after the last change (verification before completion)."""

from petru.tools import checks
from petru.trajectory import TaskSpec, run_task
from tests.fakes import FakeProvider, call, result

PASSING = "python -c \"print('all good')\""


def detected(monkeypatch, commands):
    monkeypatch.setattr(checks, "detect_checks", lambda root: list(commands))


def agent_run(tmp_path, *calls):
    provider = FakeProvider(
        [
            result(tool_calls=[call("plan", {"title": "T", "steps": ["write it"]})]),
            *[result(tool_calls=[c]) for c in calls],
            result(content="Done."),
        ]
    )
    spec = TaskSpec("python_t", "make it", ["plain"], [PASSING], "fast")
    return run_task(spec, provider=provider, repo_root=tmp_path, project=tmp_path / "p", ctx_tokens=8192)


def tool_replies(res, name):
    ids = {
        tc["id"]
        for m in res.messages
        if m.get("tool_calls")
        for tc in m["tool_calls"]
        if tc["function"]["name"] == name
    }
    return [m["content"] for m in res.messages if m.get("role") == "tool" and m.get("tool_call_id") in ids]


WRITE = call("write_file", {"path": "a.py", "content": "x = 1\n"})
DONE = call("task_complete", {"summary": "done"})


def test_completion_waits_for_green_checks_after_the_last_change(tmp_path, monkeypatch):
    detected(monkeypatch, [PASSING])
    res = agent_run(tmp_path, WRITE, DONE, call("run_checks", {}), DONE)
    first, second = tool_replies(res, "task_complete")
    assert "not verified" in first and second == "done"
    assert res.passed and res.stop_reason is None


def test_a_red_run_does_not_count_as_verification(tmp_path, monkeypatch):
    detected(monkeypatch, ['python -c "raise SystemExit(1)"'])
    res = agent_run(tmp_path, WRITE, call("run_checks", {}), DONE)
    assert "not verified" in tool_replies(res, "task_complete")[0]


def test_a_project_without_checks_completes_directly(tmp_path, monkeypatch):
    detected(monkeypatch, [])
    res = agent_run(tmp_path, WRITE, DONE)
    assert tool_replies(res, "task_complete") == ["done"]


def test_after_two_refusals_completion_is_accepted_but_marked_unverified(tmp_path, monkeypatch):
    detected(monkeypatch, [PASSING])
    res = agent_run(tmp_path, WRITE, DONE, DONE, DONE)
    replies = tool_replies(res, "task_complete")
    assert "not verified" in replies[0] and "not verified" in replies[1]
    assert replies[2].startswith("Unverified:")


def test_committing_after_green_checks_needs_no_new_run(tmp_path, monkeypatch):
    detected(monkeypatch, [PASSING])
    commit = call("git", {"action": "commit", "message": "add a"})
    res = agent_run(tmp_path, WRITE, call("run_checks", {}), commit, DONE)
    assert tool_replies(res, "task_complete") == ["done"]


def test_a_read_only_shell_command_after_green_checks_needs_no_new_run(tmp_path, monkeypatch):
    detected(monkeypatch, [PASSING])
    look = call("shell", {"command": "git status"})
    res = agent_run(tmp_path, WRITE, call("run_checks", {}), look, DONE)
    assert tool_replies(res, "task_complete") == ["done"]


def test_a_shell_command_that_changes_files_needs_a_new_run(tmp_path, monkeypatch):
    detected(monkeypatch, [PASSING])
    change = call("shell", {"command": "Set-Content -Path a.py -Value 'x = 2'"})
    res = agent_run(tmp_path, WRITE, call("run_checks", {}), change, DONE)
    assert "not verified" in tool_replies(res, "task_complete")[0]
