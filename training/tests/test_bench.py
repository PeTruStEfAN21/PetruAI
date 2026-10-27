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
