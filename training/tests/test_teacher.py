from collections import Counter
from datetime import datetime, timedelta

from petru_train import teacher


def task(root, name, difficulty):
    (root / name).mkdir(parents=True)
    path = root / name / "task.toml"
    path.write_text(f'name = "{name}"\nprompt = "p"\ndifficulty = {difficulty}\n', encoding="utf-8")
    return path


def test_interleave_goes_breadth_first_neediest_language_first_easiest_first(tmp_path):
    tasks = [
        task(tmp_path, "go_ex_hard", 8),
        task(tmp_path, "go_ex_easy", 1),
        task(tmp_path, "rust_ex_mid", 4),
        task(tmp_path, "python_ex_a", 2),
    ]
    order = teacher.interleave(tasks, Counter({"python": 5, "go": 1}))
    assert [p.parent.name for p in order] == ["rust_ex_mid", "go_ex_easy", "python_ex_a", "go_ex_hard"]


def test_run_serves_the_teacher_with_a_slot_per_parallel_attempt(tmp_path, monkeypatch):
    started, configs = [], []
    monkeypatch.setattr(teacher, "validated_tasks", lambda split: [task(tmp_path, "go_ex_a", 1)])
    monkeypatch.setattr(
        teacher, "start_server", lambda gguf, port, ctx, log, extra: started.append((ctx, extra))
    )
    monkeypatch.setattr(teacher, "wait_healthy", lambda port, timeout_s, proc: True)
    monkeypatch.setattr(teacher, "stop", lambda proc: None)

    def gen(cfg, tasks):
        configs.append(cfg)
        return {"tasks": len(tasks), "kept": {}, "attempts": {}}

    now = datetime(2026, 10, 27, 14, 0)
    teacher.run(
        now + timedelta(hours=10), parallel=3, clock=lambda: now, gen=gen, state_file=tmp_path / "s.json"
    )
    assert started == [(3 * teacher.SLOT_CTX, ("--cpu-moe", "--parallel", "3"))]
    cfg = configs[0]
    assert (
        cfg.parallel == 3 and cfg.tier == "quality" and cfg.max_minutes == 600 and cfg.samples_per_task == 1
    )
    assert cfg.base_url == f"http://127.0.0.1:{teacher.PORT}/v1"


def test_nothing_left_to_teach_starts_no_server(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(teacher, "validated_tasks", lambda split: [task(tmp_path, "go_ex_a", 1)])
    monkeypatch.setattr(
        teacher, "start_server", lambda *a, **k: (_ for _ in ()).throw(AssertionError("started"))
    )
    state = tmp_path / "s.json"
    state.write_text(json.dumps({"kept": {"go_ex_a": 1}, "attempts": {"go_ex_a": 1}}), encoding="utf-8")
    now = datetime(2026, 10, 27, 14, 0)
    assert teacher.run(now + timedelta(hours=1), clock=lambda: now, state_file=state) == {"open": 0}
    assert teacher.main_exit({"open": 0}) == teacher.NOTHING_LEFT
