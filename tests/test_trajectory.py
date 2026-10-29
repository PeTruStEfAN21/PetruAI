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


def test_run_task_isolates_global_memory(tmp_path, monkeypatch):
    real_home = tmp_path / "real-home"
    monkeypatch.setenv("PETRU_HOME", str(real_home))
    provider = FakeProvider(
        [
            result(
                tool_calls=[
                    call(
                        "remember",
                        {"name": "x", "description": "d", "type": "user", "content": "c", "scope": "global"},
                    )
                ]
            ),  # fmt: skip
            result(content="ok"),
        ]
    )
    run_task(
        spec(),
        provider=provider,
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
        max_extra_turns=0,
    )
    assert not (real_home / "memory").exists()
    assert not (tmp_path / "p" / ".petru-home").exists()
    import os

    assert os.environ["PETRU_HOME"] == str(real_home)  # restored


def test_task_result_round_trips_through_json(tmp_path):
    res = TaskResult("t", True, 1.5, 0, None, [{"role": "user", "content": "x"}], [], "ok", 0)
    path = tmp_path / "r.json"
    res.save(path)
    assert TaskResult.load(path) == res
    assert json.loads(path.read_text(encoding="utf-8"))["passed"] is True


def test_a_project_without_any_check_does_not_pass(tmp_path):
    from petru.trajectory import run_checks_for

    (tmp_path / "stats.py").write_text("print(1)\n", encoding="utf-8")  # a script, no tests
    ok, output = run_checks_for(tmp_path, [])
    assert not ok and "no checks" in output


def seeded_task(tmp_path):
    seed = tmp_path / "tasks" / "py_two" / "seed"
    seed.mkdir(parents=True)
    (seed / "two.py").write_text("def two():\n    raise NotImplementedError\n", encoding="utf-8")
    (seed / "check_two.py").write_text("from two import two\nassert two() == 2\n", encoding="utf-8")
    toml = tmp_path / "tasks" / "py_two" / "task.toml"
    toml.write_text(
        'name = "py_two"\nprompt = "make two() return 2"\nseed = "seed"\nprotect = ["check_two.py"]\n'
        'checks = ["python check_two.py"]\n',
        encoding="utf-8",
    )
    return load_task(toml)


def test_load_task_resolves_the_seed_next_to_the_toml(tmp_path):
    spec = seeded_task(tmp_path)
    assert spec.seed == tmp_path / "tasks" / "py_two" / "seed" and spec.protect == ["check_two.py"]


def finishing(*calls):
    return FakeProvider(
        [
            result(tool_calls=[call("plan", {"title": "Two", "steps": ["edit two.py"]})]),
            *[result(tool_calls=[c]) for c in calls],
            result(tool_calls=[call("task_complete", {"summary": "done"})]),
            result(content="Done."),
        ]
    )


def test_a_seeded_task_starts_from_the_committed_scaffold(tmp_path):
    import subprocess

    solve = call("write_file", {"path": "two.py", "content": "def two():\n    return 2\n"})
    res = run_task(
        seeded_task(tmp_path),
        provider=finishing(solve),
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
    )
    assert res.passed, res.check_output
    log = subprocess.run(["git", "log", "--format=%s"], cwd=tmp_path / "p", capture_output=True, text=True)
    assert log.stdout.strip().splitlines()[-1] == "Exercise scaffold"


def test_changing_the_protected_tests_does_not_pass(tmp_path):
    cheat = call("write_file", {"path": "check_two.py", "content": "pass\n"})
    res = run_task(
        seeded_task(tmp_path),
        provider=finishing(cheat),
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
    )
    assert not res.passed and "NotImplementedError" in res.check_output


def test_verify_runs_the_checks_on_the_seed_with_a_solution_on_top(tmp_path):
    from petru.trajectory import verify_task

    spec = seeded_task(tmp_path)
    solution = tmp_path / "solution"
    solution.mkdir()
    (solution / "two.py").write_text("def two():\n    return 2\n", encoding="utf-8")
    assert verify_task(spec, tmp_path / "solved", solution)[0]
    ok, output = verify_task(spec, tmp_path / "stub", None)
    assert not ok and "NotImplementedError" in output


def test_cli_verify_needs_no_model_server(tmp_path, monkeypatch):
    from petru import trajectory

    spec = seeded_task(tmp_path)
    monkeypatch.setattr(trajectory, "ServerManager", None)  # would fail if a server were started
    out = tmp_path / "r.json"
    code = trajectory.main(
        [str(tmp_path / "tasks" / "py_two" / "task.toml"), "--verify-with", str(spec.seed), "--out", str(out)]
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1 and data["passed"] is False and data["name"] == "py_two" and "check_output" in data


def test_setup_commands_run_once_the_seed_is_in_place(tmp_path):
    from petru.trajectory import verify_task

    spec = seeded_task(tmp_path)
    spec.setup = ["python -c \"open('installed.txt', 'w').write('deps')\""]
    spec.checks = ["python check_two.py", "python -c \"assert open('installed.txt').read() == 'deps'\""]
    solution = tmp_path / "solution"
    solution.mkdir()
    (solution / "two.py").write_text("def two():\n    return 2\n", encoding="utf-8")
    ok, output = verify_task(spec, tmp_path / "p", solution)
    assert ok, output
    spec.setup = ['python -c "raise SystemExit(3)"']
    ok, output = verify_task(spec, tmp_path / "q", solution)
    assert not ok and "setup failed" in output


def test_test_config_the_agent_adds_is_removed_before_the_final_check(tmp_path):
    spec = seeded_task(tmp_path)
    spec.forbid = ["conftest.py", "**/conftest.py"]
    spec.checks = ["python check_two.py", "python -c \"import os; assert not os.path.exists('conftest.py')\""]
    solve = call("write_file", {"path": "two.py", "content": "def two():\n    return 2\n"})
    game = call("write_file", {"path": "conftest.py", "content": "collect_ignore_glob = ['*']\n"})
    res = run_task(
        spec, provider=finishing(solve, game), repo_root=tmp_path, project=tmp_path / "p", ctx_tokens=8192
    )
    assert res.passed, res.check_output
    assert not (tmp_path / "p" / "conftest.py").exists()


def test_only_the_solution_files_leave_the_agents_project_for_the_final_check(tmp_path):
    spec = seeded_task(tmp_path)
    spec.solution, spec.protect = ["two.py"], []  # no protected file: the fresh copy alone must hold
    spec.checks = ["python check_two.py"]
    game = call("write_file", {"path": "check_two.py", "content": "pass\n"})  # rewrite the test itself
    sitecustom = call("write_file", {"path": "helper.py", "content": "raise SystemExit(0)\n"})
    cheat = run_task(
        spec,
        provider=finishing(game, sitecustom),
        repo_root=tmp_path,
        project=tmp_path / "a",
        ctx_tokens=8192,
    )
    assert not cheat.passed and "NotImplementedError" in cheat.check_output
    solve = call("write_file", {"path": "two.py", "content": "def two():\n    return 2\n"})
    honest = run_task(
        spec, provider=finishing(solve), repo_root=tmp_path, project=tmp_path / "b", ctx_tokens=8192
    )
    assert honest.passed, honest.check_output


def test_a_task_can_run_as_a_team(tmp_path):
    from petru.agent import team

    worker = FakeProvider(
        [
            result(tool_calls=[call("write_file", {"path": "hello.py", "content": "print('hello')\n"})]),
            result(tool_calls=[call("task_complete", {"summary": "hello.py written"})]),
            result(content="ok"),
        ]
    )
    lead = FakeProvider(
        [
            result(tool_calls=[call("choose_mode", {"mode": "team", "reason": "a simple piece"})]),
            result(tool_calls=[call("plan", {"title": "Hello", "steps": ["delegate hello.py"]})]),
            result(tool_calls=[call("delegate", {"task": "print hello", "files": ["hello.py"]})]),
            result(tool_calls=[call("task_complete", {"summary": "done"})]),
            result(content="Done."),
        ]
    )
    res = run_task(
        spec(["python hello.py"]),
        provider=lead,
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
        worker=team.Worker(provider=lambda tier: worker, ctx_tokens=8192),
    )
    assert res.passed and team.LEAD_PROMPT in res.messages[0]["content"]
    assert "delegate" in {t["function"]["name"] for t in res.tools}
    assert res.delegations == 1  # counted by the tool: a summarised transcript may lose the call
    assert res.team_choice == "team"
    assert res.authors == {"hello.py": "assistant"}


def test_a_run_goes_on_past_the_iteration_limit_like_a_user_saying_continue(tmp_path):
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
        max_iterations=1,  # every tool call ends a turn: a large project ends many
    )
    assert res.passed, res.check_output
    assert res.extra_turns == 2


def test_a_run_can_stop_once_the_lead_has_chosen(tmp_path):
    from petru.agent import team

    lead = FakeProvider(
        [
            result(tool_calls=[call("choose_mode", {"mode": "team", "reason": "a simple piece"})]),
            result(tool_calls=[call("plan", {"title": "Hello", "steps": ["delegate hello.py"]})]),
            result(tool_calls=[call("write_file", {"path": "hello.py", "content": "print('hello')\n"})]),
            result(content="Done."),
        ]
    )
    res = run_task(
        spec(["python hello.py"]),
        provider=lead,
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
        worker=team.Worker(provider=lambda tier: None, ctx_tokens=8192),
        choice_only=True,
    )
    assert (res.team_choice, res.team_reason) == ("team", "a simple piece")
    assert not res.passed and not (tmp_path / "p" / "hello.py").exists()


def test_a_run_out_of_time_stops_and_keeps_its_transcript(tmp_path):
    provider = FakeProvider([result(content="never")])
    res = run_task(
        spec(["python hello.py"]),
        provider=provider,
        repo_root=tmp_path,
        project=tmp_path / "p",
        ctx_tokens=8192,
        time_limit_s=0,
    )
    assert res.stop_reason == "time limit" and not res.passed
    assert res.messages and not provider.calls


def test_a_task_result_carries_the_prompt_version(tmp_path):
    from petru.agent.prompts import prompt_version

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
    assert res.prompt_version == prompt_version()
