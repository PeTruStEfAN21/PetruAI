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


def test_a_failing_optional_step_does_not_stop_the_night(tmp_path):
    order: list[str] = []
    state = run_nightly(
        "r1", hours=1.0, steps=recording_steps(order, fail_at="trajectories"), runs_dir=tmp_path
    )
    assert order == STEPS and state.error is None and state.done == STEPS
    assert (
        "trajectories exploded" in state.notes["trajectories"] and "optional" in state.notes["trajectories"]
    )


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


def test_eval_base_is_reused_only_when_its_signature_matches(tmp_path, monkeypatch):
    import pytest

    from petru_train import evaluate, nightly
    from petru_train.evaluate import EvalResult

    monkeypatch.setattr(evaluate, "tasks_signature", lambda *a, **k: "current")
    calls = []
    monkeypatch.setattr(
        evaluate, "evaluate", lambda gguf, **kw: calls.append(gguf) or EvalResult(0, 1.0, 0.5, {}, "current")
    )
    ctx = RunContext(run="r1", runs_dir=tmp_path, hours=1.0)
    target = ctx.baseline_dir / "eval_base.json"
    target.parent.mkdir(parents=True)
    EvalResult(0, 1.0, 0.5, {}).save(target)  # saved before signatures existed: stale
    nightly.step_eval_base(ctx)
    assert len(calls) == 1 and EvalResult.load(target).signature == "current"
    with pytest.raises(nightly.SkipStep):
        nightly.step_eval_base(ctx)  # same tasks: reused
    assert len(calls) == 1


def test_trajectories_keep_their_state_in_the_run_folder(tmp_path, monkeypatch):
    from petru_train import nightly, trajectories
    from petru_train.trajectories import TrajConfig

    seen = []
    monkeypatch.setattr(
        trajectories, "load_traj_config", lambda: TrajConfig(tasks_dir=tmp_path, out=tmp_path / "t.jsonl")
    )
    monkeypatch.setattr(trajectories, "generate", lambda cfg: seen.append(cfg) or {"kept": {}})
    monkeypatch.setattr(nightly, "step_build", lambda ctx: None)
    ctx = RunContext(run="r1", runs_dir=tmp_path, hours=3.0)
    nightly.step_trajectories(ctx)
    assert seen[0].state_file == ctx.run_dir / "trajectories.state.json"
