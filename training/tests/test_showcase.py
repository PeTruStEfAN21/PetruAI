import json
import shutil

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
    calls(
        ("delegate", {"task": "records", "files": ["src/Room.cs", "./src/TimeSlot.cs", "src\\Scheduler.cs"]})
    ),
    calls(("edit_file", {"path": "src/TimeSlot.cs", "old": "a", "new": "b"})),
]


def test_a_transcript_credits_each_file_in_the_order_it_was_written():
    assert showcase.infer_authors(MESSAGES) == {
        "src/Room.cs": "assistant",
        "src/Scheduler.cs": "lead, extended by the assistant",
        "src/TimeSlot.cs": "assistant, revised by the lead",
    }


def bench_run(tmp_path, team_row=None, transcript=None):
    bench_dir = tmp_path / "bench"
    (bench_dir / "rooms" / "seed" / "Tests").mkdir(parents=True)
    (bench_dir / "rooms" / "seed" / "Tests" / "SchedulerTests.cs").write_text("t", encoding="utf-8")
    (bench_dir / "rooms" / "task.toml").write_text(
        'name = "rooms"\nprompt = "Build a booking system."\nseed = "seed"\n', encoding="utf-8"
    )
    report = tmp_path / "runs" / "b.json"
    rows = [
        {"task": "rooms", "mode": "solo", "passed": True, "seconds": 2100.0},
        {"task": "rooms", "mode": "team", "passed": True, "seconds": 1080.0, "delegations": 1,
         "team_choice": "team", "assistant": "Qwen3.5-4B-petru.gguf", **(team_row or {})},
        {"task": "two-fer", "mode": "team", "passed": True, "seconds": 60.0},  # not a bench project
    ]  # fmt: skip
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"results": rows}), encoding="utf-8")
    runs = report.with_suffix("")
    for name in ("src/Scheduler.cs", "src/Room.cs", "src/TimeSlot.cs", "Tests/SchedulerTests.cs"):
        (runs / "rooms-team" / name).parent.mkdir(parents=True, exist_ok=True)
        (runs / "rooms-team" / name).write_text("code", encoding="utf-8")
    (runs / "two-fer-team").mkdir()
    data = transcript if transcript is not None else {"messages": MESSAGES[:2]}
    (runs / "rooms-team.json").write_text(json.dumps(data), encoding="utf-8")
    return report, bench_dir


def test_a_team_project_is_exported_with_who_wrote_what(tmp_path):
    authors = {"src/Room.cs": "assistant", "src/Scheduler.cs": "lead", "src/TimeSlot.cs": "assistant"}
    report, bench_dir = bench_run(tmp_path, transcript={"messages": [], "authors": authors})
    out = tmp_path / "showcase"
    assert showcase.export(report, out, bench_dir) == ["rooms"]
    assert (out / "rooms" / "src" / "Room.cs").read_text(encoding="utf-8") == "code"
    readme = (out / "rooms" / "SHOWCASE.md").read_text(encoding="utf-8")
    assert "Build a booking system." in readme and "Qwen3.5-4B-petru assisting" in readme
    assert "| `src/Room.cs` | assistant |" in readme and "| `src/Scheduler.cs` | lead |" in readme
    assert "| `Tests/SchedulerTests.cs` | given with the task |" in readme
    index = (out / "README.md").read_text(encoding="utf-8")
    assert "| rooms | passed | 18 min | 35 min | 1 |" in index


def test_without_recorded_authors_a_complete_transcript_is_read_in_order(tmp_path):
    report, bench_dir = bench_run(tmp_path)
    showcase.export(report, tmp_path / "showcase", bench_dir)
    readme = (tmp_path / "showcase" / "rooms" / "SHOWCASE.md").read_text(encoding="utf-8")
    assert "| `src/Scheduler.cs` | lead, extended by the assistant |" in readme


def test_a_summarised_transcript_credits_nobody_it_cannot_vouch_for(tmp_path):
    report, bench_dir = bench_run(tmp_path, team_row={"delegations": 3})  # two delegations were summarised
    showcase.export(report, tmp_path / "showcase", bench_dir)
    readme = (tmp_path / "showcase" / "rooms" / "SHOWCASE.md").read_text(encoding="utf-8")
    assert "not recorded" in readme and "| lead" not in readme and "| assistant" not in readme


def test_a_lead_that_chose_to_work_alone_is_not_shown_as_a_team(tmp_path):
    report, bench_dir = bench_run(tmp_path, team_row={"team_choice": "solo", "delegations": 0})
    showcase.export(report, tmp_path / "showcase", bench_dir)
    readme = (tmp_path / "showcase" / "rooms" / "SHOWCASE.md").read_text(encoding="utf-8")
    assert "chose to work alone" in readme


def test_a_run_without_a_kept_project_is_left_out(tmp_path):
    report, bench_dir = bench_run(tmp_path)
    shutil.rmtree(report.with_suffix("") / "rooms-team")
    assert showcase.export(report, tmp_path / "showcase", bench_dir) == []
    assert not (tmp_path / "showcase" / "rooms").exists()
