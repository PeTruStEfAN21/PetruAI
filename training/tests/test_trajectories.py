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
    assert cfg.max_tokens == 0 and cfg.base_url is None


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
    from petru_train.trajectories import INVALID_CALL

    loop_source = (Path(__file__).resolve().parents[2] / "petru" / "agent" / "loop.py").read_text("utf-8")
    assert f'f"{INVALID_CALL} {{reason}}' in loop_source


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


def test_invalid_calls_are_dropped_and_the_corrected_one_stays():
    from petru_train.trajectories import normalize_messages

    def single(call_id, name, args):
        function = {"name": name, "arguments": json.dumps(args)}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "type": "function", "function": function}],
        }

    messages = [
        {"role": "user", "content": "build it"},
        single("c1", "ask_user", {}),
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": "Invalid tool call: arguments of ask_user are not a JSON object.",
        },
        single("c2", "ask_user", {"question": "Which runner?"}),
        {"role": "tool", "tool_call_id": "c2", "content": "pytest"},
    ]
    assert normalize_messages(messages) == [messages[0], *messages[3:]]


OFFLINE = "Environment: no internet, the machine is offline. Packages: pytest"


def phased_sample(build_prompt: str) -> tuple:
    def single(call_id, name, args):
        function = {"name": name, "arguments": json.dumps(args)}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "type": "function", "function": function}],
        }

    final = (
        f"{build_prompt}\n\n## Confirmed plan: T\n1. a\n\n"
        f"## DECISIONS (final; the latest entry wins)\n# Decizii\n\n- 2026-10-27: Q -> A\n\n{OFFLINE}"
    )
    messages = [
        {"role": "system", "content": final},
        {"role": "user", "content": "build it"},
        single("c1", "ask_user", {"question": "Q"}),
        {"role": "tool", "tool_call_id": "c1", "content": "A"},
        single("c2", "plan", {"title": "T", "steps": ["a"]}),
        {"role": "tool", "tool_call_id": "c2", "content": "Plan confirmed. You are now in BUILD phase."},
        single("c3", "write_file", {"path": "a.py", "content": "x"}),
        {"role": "tool", "tool_call_id": "c3", "content": "Wrote 1 bytes to a.py"},
        {"role": "assistant", "content": "Done."},
    ]
    return final, messages


def test_a_trajectory_splits_into_design_and_build_samples_with_their_own_prompts():
    from petru_train.samples import Sample, load_design_prompt, load_system_prompt
    from petru_train.trajectories import split_by_phase

    build_prompt, design_prompt = load_system_prompt(), load_design_prompt()
    final, messages = phased_sample(build_prompt)
    sample = Sample("t", "trajectory", "petru", "local", "", "python", messages, [])
    design, build = split_by_phase(sample, build_prompt, design_prompt)
    assert (design.id, build.id) == ("t#design", "t#build")
    assert design.messages[0]["content"] == f"{design_prompt}\n\n{OFFLINE}"  # no plan, no decisions yet
    assert design.messages[1:] == messages[1:6]
    assert build.messages == [messages[0], messages[1], *messages[6:]]
    assert split_by_phase(design, build_prompt, design_prompt) == [design]
    assert split_by_phase(build, build_prompt, design_prompt) == [build]


def test_samples_that_cannot_be_split_stay_whole():
    from petru_train.samples import Sample, load_design_prompt, load_system_prompt
    from petru_train.trajectories import split_by_phase

    build_prompt, design_prompt = load_system_prompt(), load_design_prompt()
    _, messages = phased_sample(build_prompt)
    commit = Sample("c", "commit", "r", "MIT", "abc", "python", messages, [])
    unknown_prompt = Sample(
        "u", "trajectory", "p", "local", "", "python", [{"role": "system", "content": "S"}, *messages[1:]], []
    )
    no_plan = Sample("n", "trajectory", "p", "local", "", "python", messages[:4], [])
    for sample in (commit, unknown_prompt, no_plan):
        assert split_by_phase(sample, build_prompt, design_prompt) == [sample]


def test_training_loads_each_trajectory_as_its_two_phases(tmp_path):
    from petru_train.samples import Sample, load_system_prompt, write_jsonl
    from petru_train.train import load_samples

    _, messages = phased_sample(load_system_prompt())
    write_jsonl(
        tmp_path / "d.jsonl", [Sample("t", "trajectory", "petru", "local", "", "python", messages, [])]
    )
    assert [s.id for s in load_samples(tmp_path / "d.jsonl")] == ["t#design", "t#build"]


def test_prompt_sections_match_the_agent_sources():
    from petru_train.trajectories import PLAN_CONFIRMED, PROMPT_SECTIONS

    petru = Path(__file__).resolve().parents[2] / "petru"
    sources = "".join(
        (petru / rel).read_text(encoding="utf-8")
        for rel in ("agent/context.py", "agent/prompts.py", "memory/tools.py", "journal/summarize.py")
    )
    assert all(header.strip() in sources for header in PROMPT_SECTIONS)
    assert f'"{PLAN_CONFIRMED}.' in (petru / "tools" / "interaction.py").read_text(encoding="utf-8")


def test_the_build_part_sees_the_confirmed_plan_like_the_agent_did():
    from petru_train.samples import Sample, load_design_prompt, load_system_prompt
    from petru_train.trajectories import split_by_phase

    build_prompt = load_system_prompt()
    _, messages = phased_sample(build_prompt)
    after_task = f"{build_prompt}\n\n## DECISIONS (final; the latest entry wins)\n- Q -> A\n\n{OFFLINE}"
    messages = [
        {"role": "system", "content": after_task},
        *messages[1:],
    ]  # the plan section is gone at the end
    sample = Sample("t", "trajectory", "petru", "local", "", "python", messages, [])
    _, build = split_by_phase(sample, build_prompt, load_design_prompt())
    decisions = f"## DECISIONS (final; the latest entry wins)\n- Q -> A\n\n{OFFLINE}"
    assert build.messages[0]["content"] == f"{build_prompt}\n\n## Confirmed plan: T\n1. a\n\n{decisions}"


def test_no_length_limit_when_max_tokens_is_zero():
    from petru_train.trajectories import rejection_reason

    long = good(tokens=50_000)
    assert result_to_sample(long, "python_x", max_tokens=0) is not None
    assert rejection_reason(long, 0) == ""
    assert (
        TrajConfig(tasks_dir=Path("."), out=Path("t.jsonl")).max_tokens == 0
    )  # every verified example is kept


def test_tool_results_lose_terminal_color_codes():
    from petru_train.trajectories import normalize_messages

    esc = chr(27)
    messages = [{"role": "tool", "tool_call_id": "c1", "content": f"{esc}[33mwarn{esc}[39m ok"}]
    assert normalize_messages(messages)[0]["content"] == "warn ok"


def test_a_state_file_per_run_lets_every_night_generate_again(tmp_path):
    write_tasks(tmp_path / "tasks", ["python_a"])
    out = tmp_path / "traj.jsonl"

    def config(night):
        return TrajConfig(
            tasks_dir=tmp_path / "tasks", out=out, samples_per_task=1, attempts_per_task=1,
            state_file=tmp_path / night / "state.json",
        )  # fmt: skip

    generate(config("n1"), runner=lambda task, cfg, attempt: good("python_a"))
    generate(config("n2"), runner=lambda task, cfg, attempt: good("python_a", seconds=11.0))
    assert len(read_jsonl(out)) == 2 and (tmp_path / "n2" / "state.json").is_file()
