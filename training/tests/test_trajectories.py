import json
from pathlib import Path

from petru_train.samples import read_jsonl
from petru_train.trajectories import TrajConfig, generate, load_traj_config, result_to_sample

TOOLS = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]


def good(name="python_x", **overrides) -> dict:
    data = {
        "name": name,
        "passed": True,
        "seconds": 10.0,
        "tokens": 500,
        "stop_reason": None,
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "build it"},
            {"role": "assistant", "content": "done"},
        ],
        "tools": TOOLS,
        "check_output": "[PASS] pytest",
        "extra_turns": 0,
    }
    data.update(overrides)
    return data


def test_failed_or_truncated_trajectories_are_rejected():
    assert result_to_sample(good(passed=False), "python_x", max_tokens=12000) is None
    assert result_to_sample(good(stop_reason="iteration limit"), "python_x", max_tokens=12000) is None
    assert result_to_sample(good(tokens=20000), "python_x", max_tokens=12000) is None


def test_good_trajectory_keeps_the_recorded_system_prompt():
    sample = result_to_sample(good(), "python_x", max_tokens=12000)
    assert sample is not None and sample.source == "trajectory" and sample.language == "python"
    assert sample.messages[0] == {"role": "system", "content": "system prompt"} and sample.tools == TOOLS
    assert sample.messages[1] == {"role": "user", "content": "build it"}
    assert result_to_sample(good(messages=[{"role": "user", "content": "x"}]), "python_x", 12000) is None
    assert sample.repo == "python_x" and sample.id.startswith("traj:python_x:")
    assert result_to_sample(good("ts_api"), "ts_api", max_tokens=12000).language == "typescript"
    assert result_to_sample(good("flutter_app"), "flutter_app", max_tokens=12000).language == "dart"


def write_tasks(tasks_dir: Path, names: list[str]) -> None:
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (tasks_dir / f"{name}.toml").write_text(f'name = "{name}"\nprompt = "do {name}"\n', encoding="utf-8")


def test_generate_keeps_three_per_task_and_resumes(tmp_path):
    write_tasks(tmp_path / "tasks", ["python_a", "ts_b"])
    cfg = TrajConfig(
        tasks_dir=tmp_path / "tasks", out=tmp_path / "traj.jsonl", samples_per_task=3, attempts_per_task=8
    )
    calls: list[tuple[str, int]] = []

    def runner(task_path: Path, cfg: TrajConfig, attempt: int) -> dict:
        calls.append((task_path.stem, attempt))
        passed = attempt % 2 == 0
        return good(
            task_path.stem,
            passed=passed,
            messages=[
                {"role": "user", "content": f"{task_path.stem} {attempt}"},
                {"role": "assistant", "content": "done"},
            ],
        )

    stats = generate(cfg, runner=runner)
    kept = read_jsonl(cfg.out)
    assert len(kept) == 6 and stats["kept"] == {"python_a": 3, "ts_b": 3}
    assert len({s.id for s in kept}) == 6
    assert len(calls) == 12  # 6 attempts per task: 3 fail, 3 pass
    state = json.loads((tmp_path / "traj.jsonl.state.json").read_text(encoding="utf-8"))
    assert state["kept"] == {"python_a": 3, "ts_b": 3} and state["attempts"] == {"python_a": 6, "ts_b": 6}

    generate(cfg, runner=runner)
    assert len(calls) == 12 and len(read_jsonl(cfg.out)) == 6  # resumed: nothing rerun, nothing duplicated


def test_generate_gives_up_after_the_attempt_budget(tmp_path):
    write_tasks(tmp_path / "tasks", ["python_a"])
    cfg = TrajConfig(
        tasks_dir=tmp_path / "tasks", out=tmp_path / "traj.jsonl", samples_per_task=3, attempts_per_task=2
    )
    calls = []

    def runner(task_path, cfg, attempt):
        calls.append(attempt)
        return good("python_a", passed=False)

    stats = generate(cfg, runner=runner)
    assert calls == [1, 2] and stats["kept"] == {"python_a": 0} and not cfg.out.exists()


def test_generate_goes_round_robin_and_stops_at_the_time_budget(tmp_path):
    write_tasks(tmp_path / "tasks", ["flutter_a", "python_b", "ts_c"])
    clock = [0.0]
    order = []

    def runner(task_path, cfg, attempt):
        order.append((task_path.stem, attempt))
        clock[0] += 10 * 60  # every attempt takes 10 minutes
        return good(task_path.stem, passed=False)

    cfg = TrajConfig(
        tasks_dir=tmp_path / "tasks", out=tmp_path / "t.jsonl", attempts_per_task=4, max_minutes=45
    )
    generate(cfg, runner=runner, clock=lambda: clock[0])
    assert order == [("flutter_a", 1), ("python_b", 1), ("ts_c", 1), ("flutter_a", 2), ("python_b", 2)]


def test_a_hung_attempt_is_killed_and_counted_as_failed(tmp_path, monkeypatch):
    import subprocess

    from petru_train import trajectories

    killed = []

    class Hung:
        pid = 4242

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("petru", timeout)

    monkeypatch.setattr(trajectories.subprocess, "Popen", lambda *a, **k: Hung())
    monkeypatch.setattr(trajectories, "kill_tree", lambda pid: killed.append(pid))
    cfg = TrajConfig(tasks_dir=tmp_path, out=tmp_path / "t.jsonl", attempt_timeout_s=1)
    result = trajectories.run_petru_task(tmp_path / "python_a.toml", cfg, 1)
    assert result["passed"] is False and "timeout" in result["stop_reason"] and killed == [4242]


def test_kill_tree_uses_the_platform_tool(monkeypatch):
    from petru_train import nightly, trajectories

    calls = []
    monkeypatch.setattr(trajectories.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(nightly.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(trajectories.sys, "platform", "win32")
    trajectories.kill_tree(7)
    nightly.stop_llama_servers()
    monkeypatch.setattr(trajectories.sys, "platform", "linux")
    trajectories.kill_tree(7)
    nightly.stop_llama_servers()
    assert calls[0][:3] == ["taskkill", "/PID", "7"] and calls[1][0] == "taskkill"
    assert calls[2] == ["pkill", "-TERM", "-P", "7"] and calls[3] == ["kill", "-TERM", "7"]
    assert calls[4] == ["pkill", "-f", "llama-server"]


def test_load_traj_config(tmp_path):
    cfg_file = tmp_path / "trajectories.toml"
    cfg_file.write_text(
        'tasks_dir = "tasks"\nout = "data/trajectories.jsonl"\ntier = "default"\nsamples_per_task = 2\n',
        encoding="utf-8",
    )
    cfg = load_traj_config(cfg_file, base_dir=tmp_path)
    assert cfg.tasks_dir == tmp_path / "tasks" and cfg.out == tmp_path / "data" / "trajectories.jsonl"
    assert cfg.tier == "default" and cfg.samples_per_task == 2 and cfg.attempts_per_task == 4
    assert cfg.max_tokens == 12000 and cfg.base_url is None


def test_rejection_reason_names_what_went_wrong():
    from petru_train.trajectories import rejection_reason

    failing = good(
        passed=False, check_output="[PASS] dart analyze\n[FAIL] flutter test\nExpected: 1\n  Actual: 0"
    )
    assert rejection_reason(failing, max_tokens=12000) == "checks failed: [FAIL] flutter test"
    assert rejection_reason(good(stop_reason="iteration limit"), 12000) == "stopped: iteration limit"
    assert rejection_reason(good(tokens=20000), 12000) == "too long: 20000 tokens"
    assert rejection_reason(good(passed=False, check_output=""), 12000) == "checks failed"
    assert rejection_reason(good(), 12000) == ""


def test_rejected_attempts_are_kept_for_diagnosis(tmp_path, capsys):
    write_tasks(tmp_path / "tasks", ["flutter_a"])
    cfg = TrajConfig(
        tasks_dir=tmp_path / "tasks", out=tmp_path / "traj.jsonl", samples_per_task=1, attempts_per_task=1
    )
    generate(cfg, runner=lambda task, cfg, attempt: good("flutter_a", passed=False, check_output="[FAIL] x"))
    saved = json.loads((tmp_path / "rejected" / "flutter_a-1.json").read_text(encoding="utf-8"))
    assert saved["check_output"] == "[FAIL] x"
    assert "flutter_a attempt 1: rejected (0/1): checks failed: [FAIL] x" in capsys.readouterr().out


HINT = " (Use the ask_user tool for further questions, then call plan.)"
CONTINUE = (
    "Continue with the confirmed plan using tools. Run run_checks, fix failures, commit when green, "
    "then call task_complete."
)


def harness_transcript() -> list[dict]:
    def tool_call(call_id, name, args):
        function = {"name": name, "arguments": json.dumps(args)}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "type": "function", "function": function}],
        }

    return [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "build it"},
        {"role": "assistant", "content": "**Question 1:** Which runner?"},
        {"role": "user", "content": "pytest" + HINT},
        tool_call("c1", "plan", {"title": "T", "steps": ["a"]}),
        {"role": "tool", "tool_call_id": "c1", "content": "Plan confirmed."},
        {"role": "assistant", "content": "I will now write the files."},
        {"role": "user", "content": CONTINUE},
        tool_call("c2", "task_complete", {"summary": "done"}),
        {"role": "tool", "tool_call_id": "c2", "content": "done"},
        {"role": "assistant", "content": "Done."},
    ]


def test_harness_corrections_become_the_behaviour_to_learn():
    from petru_train.trajectories import normalize_messages

    out = normalize_messages(harness_transcript())
    roles = ["system", "user", "assistant", "tool", "assistant", "tool", "assistant", "tool", "assistant"]
    assert [m["role"] for m in out] == roles
    ask = out[2]["tool_calls"][0]["function"]
    assert ask["name"] == "ask_user" and json.loads(ask["arguments"]) == {
        "question": "**Question 1:** Which runner?"
    }
    assert out[3] == {"role": "tool", "tool_call_id": out[2]["tool_calls"][0]["id"], "content": "pytest"}
    assert not any(HINT in str(m.get("content")) or m.get("content") == CONTINUE for m in out)
    assert normalize_messages(out) == out


def test_kept_trajectories_are_normalized():
    sample = result_to_sample(good(messages=harness_transcript()), "python_x", max_tokens=12000)
    assert sample is not None and sample.messages[2]["tool_calls"][0]["function"]["name"] == "ask_user"


def test_training_loads_trajectory_samples_normalized(tmp_path):
    from petru_train.samples import Sample, write_jsonl
    from petru_train.train import load_samples

    traj = Sample("t", "trajectory", "petru", "local", "", "python", harness_transcript(), [])
    commit = Sample("c", "commit", "r", "MIT", "abc", "python", [{"role": "user", "content": "x" + HINT}], [])
    write_jsonl(tmp_path / "d.jsonl", [traj, commit])
    loaded = load_samples(tmp_path / "d.jsonl")
    assert loaded[0].messages[2]["tool_calls"][0]["function"]["name"] == "ask_user"
    assert loaded[1].messages == commit.messages  # only trajectories are rewritten


def test_harness_markers_match_the_agent_harness():
    from petru_train.trajectories import CONTINUE_PREFIX, DESIGN_HINT

    source = (Path(__file__).resolve().parents[2] / "petru" / "trajectory.py").read_text(encoding="utf-8")
    assert DESIGN_HINT.strip() in source and CONTINUE_PREFIX in source
    from petru_train.trajectories import QUESTION_GUARDS

    tools_source = (Path(__file__).resolve().parents[2] / "petru" / "tools" / "interaction.py").read_text(
        "utf-8"
    )
    assert all(guard in tools_source for guard in QUESTION_GUARDS)


def test_repeated_or_excess_questions_are_dropped_from_the_transcript():
    from petru_train.trajectories import normalize_messages

    def ask(call_id, question):
        function = {"name": "ask_user", "arguments": json.dumps({"question": question})}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "type": "function", "function": function}],
        }

    messages = [
        {"role": "user", "content": "build it"},
        ask("c1", "Which runner?"),
        {"role": "tool", "tool_call_id": "c1", "content": "pytest"},
        ask("c2", "Which runner?"),
        {
            "role": "tool",
            "tool_call_id": "c2",
            "content": "You already asked this question. The user answered: pytest.",
        },
        ask("c3", "One more?"),
        {
            "role": "tool",
            "tool_call_id": "c3",
            "content": "That is enough design questions (8 answered). Call plan.",
        },
    ]
    assert normalize_messages(messages) == messages[:3]
