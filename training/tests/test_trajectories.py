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
