import json

from petru_train import showcase


def calls(*pairs):
    return {
        "role": "assistant",
        "tool_calls": [
            {"id": str(i), "function": {"name": name, "arguments": json.dumps(args)}}
            for i, (name, args) in enumerate(pairs)
        ],
    }


MESSAGES = [
    calls(("write_file", {"path": "src/Scheduler.cs", "content": "x"})),
    calls(("delegate", {"task": "records", "files": ["src/Room.cs", "./src/TimeSlot.cs"]})),
    calls(("edit_file", {"path": "src/TimeSlot.cs", "old": "a", "new": "b"})),
]


def test_each_file_is_credited_to_whoever_wrote_it():
    authors = showcase.authors(MESSAGES, given={"Tests/SchedulerTests.cs"})
    assert authors("src/Scheduler.cs") == "lead"
    assert authors("src/Room.cs") == "assistant"
    assert authors("src/TimeSlot.cs") == "assistant, revised by the lead"
    assert authors("Tests/SchedulerTests.cs") == "given (acceptance tests)"


def bench_run(tmp_path):
    bench_dir = tmp_path / "bench"
    (bench_dir / "rooms" / "seed" / "Tests").mkdir(parents=True)
    (bench_dir / "rooms" / "seed" / "Tests" / "SchedulerTests.cs").write_text("t", encoding="utf-8")
    (bench_dir / "rooms" / "task.toml").write_text(
        'name = "rooms"\nprompt = "Build a booking system."\nseed = "seed"\n', encoding="utf-8"
    )
    report = tmp_path / "runs" / "b.json"
    rows = [
        {"task": "rooms", "mode": "solo", "passed": True, "seconds": 2100.0, "tokens": 18000},
        {"task": "rooms", "mode": "team", "passed": True, "seconds": 1080.0, "tokens": 15500,
         "delegations": 1, "team_choice": "team"},
    ]  # fmt: skip
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"results": rows}), encoding="utf-8")
    project = report.with_suffix("") / "rooms-team"
    for name in ("src/Scheduler.cs", "src/Room.cs", "src/TimeSlot.cs", "Tests/SchedulerTests.cs"):
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text("code", encoding="utf-8")
    (report.with_suffix("") / "rooms-team.json").write_text(
        json.dumps({"messages": MESSAGES}), encoding="utf-8"
    )
    return report, bench_dir


def test_a_team_project_is_exported_with_who_wrote_what(tmp_path):
    report, bench_dir = bench_run(tmp_path)
    out = tmp_path / "showcase"
    showcase.export(report, out, bench_dir)
    assert (out / "rooms" / "src" / "Room.cs").read_text(encoding="utf-8") == "code"
    readme = (out / "rooms" / "SHOWCASE.md").read_text(encoding="utf-8")
    assert "Build a booking system." in readme
    assert "| `src/Room.cs` | assistant |" in readme and "| `src/Scheduler.cs` | lead |" in readme
    index = (out / "README.md").read_text(encoding="utf-8")
    assert "| rooms | passed | 18 min | 35 min | 1 |" in index


def test_a_run_without_a_kept_project_is_left_out(tmp_path):
    report, bench_dir = bench_run(tmp_path)
    import shutil

    shutil.rmtree(report.with_suffix("") / "rooms-team")
    showcase.export(report, tmp_path / "showcase", bench_dir)
    assert not (tmp_path / "showcase" / "rooms").exists()
