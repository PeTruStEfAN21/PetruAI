"""Team mode: the lead delegates small, self-contained tasks to a faster assistant model."""

from pathlib import Path

from petru.agent import team
from petru.agent.loop import Agent
from petru.agent.state import Session
from petru.tools import checks
from petru.tools.registry import default_registry
from petru.tui.port import ScriptedUI
from tests.fakes import FakeProvider, call, result

TASK = "Write a.py with x = 1. Only a.py."


def lead_with(tmp_path, lead_steps, worker_steps):
    worker = FakeProvider([result(tool_calls=[c]) for c in worker_steps] + [result(content="ok")])
    registry = default_registry(False)
    team.lead_registry(registry, team.Worker(provider=lambda: worker, ctx_tokens=8192))
    lead = FakeProvider(
        [result(tool_calls=[call("plan", {"title": "T", "steps": ["delegate a.py"]})])]
        + [result(tool_calls=[c]) for c in lead_steps]
        + [result(content="Done.")]
    )
    session = Session(tmp_path, role=team.LEAD_PROMPT)
    agent = Agent(lead, registry, ScriptedUI(), session, tmp_path, 8192, False)
    agent.run_turn("build it")
    return session, worker


def replies(session, name):
    ids = {
        tc["id"]
        for m in session.messages
        if m.get("tool_calls")
        for tc in m["tool_calls"]
        if tc["function"]["name"] == name
    }
    return [
        m["content"] for m in session.messages if m.get("role") == "tool" and m.get("tool_call_id") in ids
    ]


def test_the_assistant_writes_only_the_files_it_was_given(tmp_path):
    delegate = call("delegate", {"task": TASK, "files": ["a.py"]})
    worker_steps = [
        call("write_file", {"path": "b.py", "content": "y = 2\n"}),
        call("write_file", {"path": "a.py", "content": "x = 1\n"}),
        call("task_complete", {"summary": "a.py written"}),
    ]
    session, _ = lead_with(tmp_path, [delegate, call("task_complete", {"summary": "done"})], worker_steps)
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n" and not (tmp_path / "b.py").exists()
    [report] = replies(session, "delegate")
    assert "a.py written" in report and "a.py" in report


def test_the_assistant_works_in_its_own_context_on_the_task_alone(tmp_path):
    delegate = call("delegate", {"task": TASK, "files": ["a.py"]})
    worker_steps = [
        call("write_file", {"path": "a.py", "content": "x = 1\n"}),
        call("task_complete", {"summary": "ok"}),
    ]
    _, worker = lead_with(tmp_path, [delegate, call("task_complete", {"summary": "done"})], worker_steps)
    first = worker.calls[0]["messages"]
    assert first[0]["role"] == "system" and team.WORKER_PROMPT.split(".")[0] in first[0]["content"]
    assert first[1] == {"role": "user", "content": team.worker_request(TASK, ["a.py"], [])}
    assert not any("build it" in str(m.get("content")) for m in first)  # nothing of the lead's conversation
    tools = {t["function"]["name"] for t in worker.calls[0]["tools"]}
    assert (
        "delegate" not in tools and "shell" not in tools and "ask_user" not in tools and "write_file" in tools
    )


def test_the_lead_prompt_and_the_delegate_tool_reach_the_lead(tmp_path):
    session, _ = lead_with(tmp_path, [call("task_complete", {"summary": "done"})], [])
    assert team.LEAD_PROMPT in session.messages[0]["content"]


def test_delegated_changes_must_pass_the_leads_checks_before_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "detect_checks", lambda root: ["python -c \"print('ok')\""])
    delegate = call("delegate", {"task": TASK, "files": ["a.py"]})
    worker_steps = [
        call("write_file", {"path": "a.py", "content": "x = 1\n"}),
        call("run_checks", {}),
        call("task_complete", {"summary": "ok"}),
    ]
    lead_steps = [
        delegate,
        call("task_complete", {"summary": "done"}),
        call("run_checks", {}),
        call("task_complete", {"summary": "done"}),
    ]
    session, _ = lead_with(tmp_path, lead_steps, worker_steps)
    first, second = replies(session, "task_complete")
    assert "not verified" in first and second == "done"


def write(path, content="x = 1\n"):
    return call("write_file", {"path": path, "content": content})


def choose(mode, reason="r"):
    return call("choose_mode", {"mode": mode, "reason": reason})


def test_the_lead_may_start_with_one_file_then_must_delegate_before_creating_more(tmp_path):
    delegate = call("delegate", {"task": "Write c.py with z = 3.", "files": ["c.py"]})
    worker_steps = [write("c.py", "z = 3\n"), call("task_complete", {"summary": "c.py written"})]
    done = call("task_complete", {"summary": "done"})
    lead_steps = [choose("team"), write("a.py"), write("b.py"), delegate, write("b.py"), done]
    session, _ = lead_with(tmp_path, lead_steps, worker_steps)
    _, refused, allowed = replies(session, "write_file")
    assert "delegate" in refused and "delegate" not in allowed
    assert all((tmp_path / name).is_file() for name in ("a.py", "b.py", "c.py"))


def test_the_lead_may_always_rewrite_a_file_that_exists(tmp_path):
    done = call("task_complete", {"summary": "done"})
    lead_steps = [choose("team"), write("a.py"), write("a.py", "x = 2\n"), done]
    lead_with(tmp_path, lead_steps, [])
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 2\n"


def test_the_lead_may_write_test_files_of_its_own_at_any_time(tmp_path):
    names = ["a.py", "test_b.py", "b_test.go", "BTests.cs", "c.test.ts", "tests/helpers.py"]
    steps = [choose("team"), *map(write, names), call("task_complete", {"summary": "done"})]
    session, _ = lead_with(tmp_path, steps, [])
    assert not any("Team mode" in reply for reply in replies(session, "write_file"))
    assert all((tmp_path / name).is_file() for name in names)


def test_a_name_that_only_contains_test_is_not_a_test_file():
    assert not team.is_test_file(Path("latest.go")) and not team.is_test_file(Path("contest/rules.py"))


def test_the_lead_decides_whether_the_project_needs_the_team_before_it_creates_a_file(tmp_path):
    done = call("task_complete", {"summary": "done"})
    steps = [write("a.py"), choose("solo", "one small file"), write("a.py"), done]
    session, _ = lead_with(tmp_path, steps, [])
    refused, allowed = replies(session, "write_file")
    assert "choose_mode" in refused and "choose_mode" not in allowed


def test_a_lead_that_works_alone_may_create_every_file_itself(tmp_path):
    done = call("task_complete", {"summary": "done"})
    session, _ = lead_with(tmp_path, [choose("solo"), write("a.py"), write("b.py"), write("c.py"), done], [])
    assert not any("Team mode" in reply for reply in replies(session, "write_file"))
    assert all((tmp_path / name).is_file() for name in ("a.py", "b.py", "c.py"))


def test_the_choice_is_final(tmp_path):
    done = call("task_complete", {"summary": "done"})
    lead_steps = [choose("team"), choose("solo"), write("a.py"), write("b.py"), done]
    session, _ = lead_with(tmp_path, lead_steps, [])
    assert "final" in replies(session, "choose_mode")[1]
    assert not (tmp_path / "b.py").exists()  # still a team: b.py waits for a delegation


def test_a_new_task_lets_the_lead_choose_again():
    registry = default_registry(False)
    team.lead_registry(registry, team.Worker(provider=lambda: None, ctx_tokens=8192))
    registry.get("choose_mode").mode, registry.get("write_file").created = "solo", 3
    registry.get("delegate").calls = 2
    team.start_task(registry)
    assert registry.get("choose_mode").mode is None and registry.get("write_file").created == 0
    assert registry.get("delegate").calls == 0
    team.start_task(default_registry(False))  # a registry without the team's tools is left alone
