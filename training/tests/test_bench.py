import json

from petru_train import bench


def task(root, name):
    (root / name).mkdir(parents=True)
    path = root / name / "task.toml"
    path.write_text(f'name = "{name}"\nprompt = "p"\n', encoding="utf-8")
    return path


def test_every_task_runs_solo_and_as_a_team_in_alternating_order(tmp_path):
    tasks = [task(tmp_path, "py_a"), task(tmp_path, "go_b")]
    calls = []

    def runner(path, mode):
        calls.append((path.parent.name, mode))
        return {
            "passed": mode == "team",
            "seconds": 10.0 if mode == "team" else 20.0,
            "tokens": 5,
            "delegations": 1,
        }

    report = bench.compare(tasks, runner, tmp_path / "report.json")
    assert calls == [("py_a", "solo"), ("py_a", "team"), ("go_b", "team"), ("go_b", "solo")]
    assert report["summary"]["team"] == {"passed": 2, "tasks": 2, "pass_rate": 1.0, "mean_seconds": 10.0}
    assert report["summary"]["solo"]["pass_rate"] == 0.0
    saved = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert len(saved["results"]) == 4


def test_the_comparison_resumes_from_its_report(tmp_path):
    tasks = [task(tmp_path, "py_a")]
    out = tmp_path / "report.json"
    first = {"task": "py_a", "mode": "solo", "passed": True, "seconds": 1.0, "tokens": 1, "delegations": 0}
    out.write_text(json.dumps({"results": [first]}), encoding="utf-8")
    calls = []
    bench.compare(tasks, lambda path, mode: calls.append(mode) or {"passed": False, "seconds": 2.0}, out)
    assert calls == ["team"]


def test_a_run_counts_its_delegations():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [{"id": "1", "function": {"name": "delegate", "arguments": "{}"}}],
        },
        {
            "role": "assistant",
            "tool_calls": [{"id": "2", "function": {"name": "run_checks", "arguments": "{}"}}],
        },
    ]
    assert bench.delegations(messages) == 1


def test_a_run_keeps_its_transcript_for_later_reading(tmp_path):
    out = tmp_path / "result.json"
    data = {"passed": True, "seconds": 3.0, "tokens": 9, "stop_reason": None, "messages": []}
    out.write_text(json.dumps(data), encoding="utf-8")
    keep = tmp_path / "transcripts" / "py_a-team.json"
    row = bench.read_result(out, keep)
    assert row == {
        "passed": True,
        "seconds": 3.0,
        "tokens": 9,
        "stop_reason": None,
        "delegations": 0,
        "team_choice": None,
    }
    assert json.loads(keep.read_text(encoding="utf-8")) == data


def test_the_delegation_count_comes_from_the_result_when_it_has_one(tmp_path):
    out = tmp_path / "result.json"
    out.write_text(json.dumps({"passed": True, "delegations": 4, "messages": []}), encoding="utf-8")
    assert bench.read_result(out)["delegations"] == 4


def test_a_run_reports_whether_the_lead_chose_the_team(tmp_path):
    out = tmp_path / "result.json"
    out.write_text(json.dumps({"passed": True, "team_choice": "solo", "messages": []}), encoding="utf-8")
    assert bench.read_result(out)["team_choice"] == "solo"


def test_a_finished_project_is_kept_without_its_build_output(tmp_path):
    project = tmp_path / "project"
    built = ("bin/Debug/a.dll", "obj/x.json", "node_modules/m/i.js", ".git/HEAD")
    for name in ("src/Ledger.cs", "go.mod", *built):
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text("x", encoding="utf-8")
    dest = tmp_path / "kept"
    bench.keep_project(project, dest)
    kept = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert kept == ["go.mod", "src/Ledger.cs"]


class FakeRun:
    """Stands in for petru.trajectory: writes one source file into the project and a result."""

    def __init__(self, cmd, **_):
        project = cmd[cmd.index("--project") + 1]
        out = cmd[cmd.index("--out") + 1]
        (bench.Path(project) / "main.go").parent.mkdir(parents=True, exist_ok=True)
        (bench.Path(project) / "main.go").write_text("package main\n", encoding="utf-8")
        bench.Path(out).write_text(json.dumps({"passed": True, "messages": []}), encoding="utf-8")

    def wait(self, timeout):
        return 0


def test_a_run_keeps_the_project_it_built_next_to_its_transcript(tmp_path, monkeypatch):
    monkeypatch.setattr(bench.subprocess, "Popen", FakeRun)
    keep = tmp_path / "transcripts" / "go_a-team.json"
    bench.run_mode(tmp_path / "task.toml", "team", "lead", "worker", keep)
    kept = tmp_path / "transcripts" / "go_a-team" / "main.go"
    assert kept.read_text(encoding="utf-8") == "package main\n"


def test_the_assistant_is_the_promoted_fine_tune_once_there_is_one(tmp_path):
    assert bench.assistant_gguf(tmp_path) == bench.BASE_GGUF
    (tmp_path / bench.TUNED_FILE).write_bytes(b"gguf")
    assert bench.assistant_gguf(tmp_path) == tmp_path / bench.TUNED_FILE


def test_a_team_run_names_its_assistant_model(tmp_path, monkeypatch):
    monkeypatch.setattr(bench.subprocess, "Popen", FakeRun)
    row = bench.run_mode(tmp_path / "task.toml", "team", "lead", "worker", assistant="Qwen3.5-4B-petru.gguf")
    assert row["assistant"] == "Qwen3.5-4B-petru.gguf"
    assert "assistant" not in bench.run_mode(tmp_path / "task.toml", "solo", "lead", "worker", assistant="x")


BIG_TASK = """name = "big"
bench_minutes = 180
"""


class TimedRun(FakeRun):
    waited: list = []

    def wait(self, timeout):
        TimedRun.waited.append(timeout)
        return 0


def test_a_large_task_can_give_its_attempts_more_time(tmp_path, monkeypatch):
    monkeypatch.setattr(bench.subprocess, "Popen", TimedRun)
    task = tmp_path / "task.toml"
    task.write_text(BIG_TASK, encoding="utf-8")
    bench.run_mode(task, "solo", "lead", "worker")
    bench.run_mode(tmp_path / "small.toml", "solo", "lead", "worker")
    assert TimedRun.waited == [180 * 60, bench.ATTEMPT_TIMEOUT_S]
