import json

from petru.trajectory import TaskResult, TaskSpec, load_task, run_task
from tests.fakes import FakeProvider, call, result

TASK_TOML = """\
name = "python_hello"
prompt = "Create hello.py that prints hello. Ask me your design questions first."
answers = ["plain script", "no tests"]
checks = ["python hello.py"]
tier = "fast"
"""


def test_load_task_parses_toml(tmp_path):
    path = tmp_path / "python_hello.toml"
    path.write_text(TASK_TOML, encoding="utf-8")
    spec = load_task(path)
    assert spec == TaskSpec(
        name="python_hello",
        prompt="Create hello.py that prints hello. Ask me your design questions first.",
        answers=["plain script", "no tests"],
        checks=["python hello.py"],
        tier="fast",
    )


def test_load_task_defaults(tmp_path):
    path = tmp_path / "t.toml"
    path.write_text('prompt = "do x"\n', encoding="utf-8")
    spec = load_task(path)
    assert spec.name == "t" and spec.answers == [] and spec.checks == [] and spec.tier == "quality"


def spec(checks=None):
    return TaskSpec("python_hello", "make hello.py", ["plain"], checks or [], "fast")


def test_run_task_passes_when_checks_pass(tmp_path):
    provider = FakeProvider(
        [
            result(tool_calls=[call("plan", {"title": "Hello", "steps": ["write hello.py"]})]),
            result(tool_calls=[call("write_file", {"path": "hello.py", "content": "print('hello')\n"})]),
            result(tool_calls=[call("task_complete", {"summary": "done"})]),
            result(content="Done."),
        ]
    )
    res = run_task(
        spec(["python hello.py"]),
        provider=provider,
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
    )
    assert isinstance(res, TaskResult) and res.passed and res.name == "python_hello"
    assert res.messages[0]["role"] == "system" and res.tools and res.stop_reason is None
    assert "hello" in res.check_output and res.seconds >= 0 and (tmp_path / "p" / ".git").is_dir()
    assert res.extra_turns == 0


def test_run_task_continues_when_model_stops_early_then_fails_on_turn_limit(tmp_path):
    provider = FakeProvider(
        [
            result(tool_calls=[call("plan", {"title": "Hello", "steps": ["write hello.py"]})]),
            result(content="I will write it next."),
            result(content="Still thinking."),
            result(content="Almost."),
        ]
    )
    res = run_task(
        spec(),
        provider=provider,
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
        max_extra_turns=2,
    )
    assert not res.passed and res.stop_reason is None and res.extra_turns == 2
    user_messages = [m for m in res.messages if m["role"] == "user"]
    assert len(user_messages) == 3 and "Continue" in user_messages[-1]["content"]


def test_run_task_fails_when_a_check_fails(tmp_path):
    provider = FakeProvider(
        [
            result(tool_calls=[call("plan", {"title": "Hello", "steps": ["write hello.py"]})]),
            result(tool_calls=[call("write_file", {"path": "hello.py", "content": "raise SystemExit(3)\n"})]),
            result(tool_calls=[call("task_complete", {"summary": "done"})]),
            result(content="Done."),
        ]
    )
    res = run_task(
        spec(["python hello.py"]),
        provider=provider,
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
    )
    assert not res.passed and "[FAIL] python hello.py" in res.check_output


def test_task_result_round_trips_through_json(tmp_path):
    res = TaskResult("t", True, 1.5, 0, None, [{"role": "user", "content": "x"}], [], "ok", 0)
    path = tmp_path / "r.json"
    res.save(path)
    assert TaskResult.load(path) == res
    assert json.loads(path.read_text(encoding="utf-8"))["passed"] is True
