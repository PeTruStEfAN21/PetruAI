"""The interactive REPL end to end, driven through prompt_toolkit's pipe input instead of a console."""

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from petru import cli
from tests.fakes import call, result
from tests.test_cli import FakeManager, patch_runtime


def run_repl(monkeypatch, tmp_path, scripted, lines):
    home = tmp_path / "home"
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PETRU_HOME", str(home / ".petru"))
    project = tmp_path / "project"
    providers = patch_runtime(monkeypatch, tmp_path, scripted)
    with create_pipe_input() as pipe:
        pipe.send_text("".join(f"{line}\r" for line in lines) + "\x04")  # Ctrl+D after the last line
        with create_app_session(input=pipe, output=DummyOutput()):
            code = cli.main(["--project", str(project), "--model", "fast"])
    return code, project, providers


def test_repl_session_from_question_to_built_file(tmp_path, monkeypatch, capsys):
    scripted = [
        result(
            tool_calls=[
                call("ask_user", {"question": "Which test runner?", "options": ["pytest", "unittest"]})
            ]
        ),
        result(
            tool_calls=[
                call("plan", {"title": "Hello", "steps": ["write hello.py"], "decisions": ["pytest"]})
            ]
        ),
        result(tool_calls=[call("write_file", {"path": "hello.py", "content": "print('hi')\n"})]),
        result(content="Built hello.py."),
    ]
    lines = ["/help", "/status", "/model nope", "/plan", "make hello", "1", "", "/plan", "/status", "/done",
             "/yolo", "/memory", "/bogus", "/exit"]  # fmt: skip
    code, project, providers = run_repl(monkeypatch, tmp_path, scripted, lines)
    out = capsys.readouterr().out
    assert code == 0 and FakeManager.instances[0].stopped
    for expected in [
        "Petru ready. phase=idle",
        "/quick",
        "Unknown tier 'nope'",
        "No plan yet.",
        "? Which test runner?",
        "Plan: Hello",
        "Built hello.py.",
        "Plan (confirmed): Hello",
        "phase=build",
        "Task closed",
        "yolo on",
        "No memories yet.",
        "Unknown command /bogus",
    ]:
        assert expected in out, expected
    assert (project / "hello.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert "pytest" in (project / ".petru" / "DECISIONS.md").read_text(encoding="utf-8")
    answer = providers[0].calls[1]["messages"][-1]
    assert answer["role"] == "tool" and "pytest" in answer["content"]
    assert (tmp_path / "home" / ".petru" / "history").is_file()


def test_repl_survives_a_crashing_turn_and_ctrl_d_quits(tmp_path, monkeypatch, capsys):
    code, _, _ = run_repl(monkeypatch, tmp_path, [], ["/quick do it", "/status"])  # no scripted reply: crash
    out = capsys.readouterr().out
    assert code == 0 and "Model request failed 3 times" in out
    assert "phase=build" in out.split("Model request failed")[1]  # the REPL went on to the next command


def test_details_show_the_context_the_replies_and_the_last_stop(tmp_path, monkeypatch, capsys):
    from petru.providers.base import ChatResult

    reply = ChatResult("Fixed.", [], "stop", prompt_tokens=8192, completion_tokens=120)
    code, _, _ = run_repl(monkeypatch, tmp_path, [reply], ["/details", "/quick fix it", "/details"])
    out = capsys.readouterr().out
    before, after = out.split("Fixed.")
    assert code == 0 and "0 requests" in before and "none yet" in before
    assert "8,192 of 32,768 tokens (25%)" in after and "1 request, 120 tokens" in after
    assert "answered" in after and "team     off" in after


def test_team_switches_on_and_off_between_tasks(tmp_path, monkeypatch, capsys):
    lead = [
        result(tool_calls=[call("choose_mode", {"mode": "solo", "reason": "one small file"})]),
        result(content="Done alone."),
    ]
    lines = ["/team", "/details", "/quick add a flag", "/team", "/done", "/team", "/details"]
    code, _, providers = run_repl(monkeypatch, tmp_path, lead, lines)
    out = capsys.readouterr().out
    assert code == 0 and "Team mode on: quality leads" in out
    assert "team     on: not chosen yet" in out and "Finish the current task first" in out
    assert "team     off" in out.split("Team mode off")[1]
    first = providers[0].calls[0]
    assert {"delegate", "choose_mode"} <= {t["function"]["name"] for t in first["tools"]}
    from tests.test_cli import FakeManager

    lead_manager, worker_manager = FakeManager.instances
    assert lead_manager.started == ["fast", "quality"] and worker_manager.stopped


def test_think_switches_reasoning_on_and_off(tmp_path, monkeypatch, capsys):
    code, _, providers = run_repl(monkeypatch, tmp_path, [], ["/think", "/status", "/think"])
    out = capsys.readouterr().out
    assert code == 0 and "think on" in out and "think off" in out.split("think on")[1]
    assert " think" in out.split("phase=idle")[2]  # /status names it while on
    assert providers[0].thinking is False


def test_model_auto_picks_a_tier_for_the_project(tmp_path, monkeypatch, capsys):
    code, _, _ = run_repl(monkeypatch, tmp_path, [], ["/model auto"])
    out = capsys.readouterr().out
    from tests.test_cli import FakeManager

    assert code == 0 and "Model tier: default" in out
    assert FakeManager.instances[0].started == ["fast", "default"]
