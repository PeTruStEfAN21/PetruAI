import json

from petru_train.nightly import STEPS, RunContext, RunState, load_state, run_nightly


def recording_steps(order: list[str], fail_at: str | None = None, skip_at: str | None = None):
    def make(name):
        def step(ctx: RunContext) -> None:
            order.append(name)
            if name == fail_at:
                raise RuntimeError(f"{name} exploded")
            if name == skip_at:
                ctx.skip(f"{name} skipped: gate not passed")

        return step

    return {name: make(name) for name in STEPS}


def test_steps_are_the_documented_pipeline():
    assert STEPS == ["build", "trajectories", "train", "export", "eval_base", "eval_cand", "promote"]


def test_fresh_run_executes_every_step_and_persists_state(tmp_path):
    order: list[str] = []
    state = run_nightly("r1", hours=1.0, steps=recording_steps(order), runs_dir=tmp_path)
    assert order == STEPS and state.done == STEPS and state.error is None
    saved = json.loads((tmp_path / "r1" / "state.json").read_text(encoding="utf-8"))
    assert saved["done"] == STEPS and saved["run"] == "r1" and saved["started"] and saved["updated"]


def test_resume_skips_completed_steps(tmp_path):
    (tmp_path / "r1").mkdir()
    RunState("r1", ["build", "trajectories"], "2026-10-27T01:00:00", "2026-10-27T02:00:00", None).save(
        tmp_path / "r1"
    )
    order: list[str] = []
    state = run_nightly("r1", hours=1.0, steps=recording_steps(order), runs_dir=tmp_path)
    assert order == ["train", "export", "eval_base", "eval_cand", "promote"] and state.done == STEPS


def test_failing_step_records_the_error_and_stops(tmp_path):
    order: list[str] = []
    state = run_nightly("r1", hours=1.0, steps=recording_steps(order, fail_at="train"), runs_dir=tmp_path)
    assert order == ["build", "trajectories", "train"]
    assert state.done == ["build", "trajectories"] and "train exploded" in (state.error or "")
    assert load_state(tmp_path / "r1").error == state.error


def test_skipped_promotion_is_not_a_failure(tmp_path):
    order: list[str] = []
    state = run_nightly("r1", hours=1.0, steps=recording_steps(order, skip_at="promote"), runs_dir=tmp_path)
    assert order == STEPS and state.error is None and state.done == STEPS
    assert "gate not passed" in state.notes["promote"]


def test_skip_flags_mark_steps_done_without_running_them(tmp_path):
    order: list[str] = []
    state = run_nightly(
        "r1", hours=1.0, steps=recording_steps(order), runs_dir=tmp_path, skip=["trajectories"]
    )
    assert "trajectories" not in order and state.done == STEPS and "skipped" in state.notes["trajectories"]


def test_train_receives_the_remaining_time_budget(tmp_path):
    clock = [0.0]
    budgets: list[float | None] = []
    steps = recording_steps([])

    def build(ctx: RunContext) -> None:
        clock[0] += 30 * 60  # the build took 30 minutes

    def train(ctx: RunContext) -> None:
        budgets.append(ctx.remaining_minutes())

    steps["build"], steps["train"] = build, train
    run_nightly("r1", hours=2.0, steps=steps, runs_dir=tmp_path, clock=lambda: clock[0])
    assert budgets == [90.0]


def test_run_context_paths(tmp_path):
    ctx = RunContext(run="r1", runs_dir=tmp_path, hours=1.0)
    assert ctx.run_dir == tmp_path / "r1" and ctx.baseline_dir == tmp_path / "baseline"
