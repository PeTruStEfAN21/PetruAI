import json
from pathlib import Path

from petru_train import specialist_night as night
from petru_train.evaluate import EvalResult
from petru_train.samples import Sample, write_jsonl
from petru_train.specialists import Specialist
from petru_train.train import TrainReport

PY = Specialist("python", languages=["python"], tasks=["python"])
GO = Specialist("go", languages=["go"], tasks=["go"])


def data(tmp_path: Path, n_train: int, n_eval: int = 2, language: str = "python") -> tuple[Path, Path]:
    def sample(i: int) -> Sample:
        return Sample(
            f"r:{i}", "commit", "repo", "MIT", "c", language, [{"role": "user", "content": str(i)}], []
        )

    train, eval_ = tmp_path / "train.jsonl", tmp_path / "eval.jsonl"
    write_jsonl(train, [sample(i) for i in range(n_train)])
    write_jsonl(eval_, [sample(1000 + i) for i in range(n_eval)])
    return train, eval_


class Fakes:
    def __init__(self, cand_loss: float = 0.8, cand_pass: float = 1.0) -> None:
        self.calls: list[str] = []
        self.cand_loss, self.cand_pass = cand_loss, cand_pass

    def train(self, cfg, out_dir: Path) -> TrainReport:
        self.calls.append(f"train:{cfg.train_file.parent.parent.name}")
        report = TrainReport(
            steps=3, train_loss=1.0, eval_loss=self.cand_loss, minutes=1.0, adapter_dir="adapter",
            resumed_from=None, samples=40, base_eval_loss=1.0, context=1024,
        )  # fmt: skip
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "train_report.json").write_text(json.dumps(report.__dict__), encoding="utf-8")
        return report

    def export(self, out_dir: Path, base_model: Path) -> Path:
        self.calls.append("export")
        gguf = out_dir / "candidate-Q4_K_M.gguf"
        gguf.write_bytes(b"gguf")
        return gguf

    def evaluate(self, gguf: Path, tasks, log) -> EvalResult:
        self.calls.append(f"eval:{gguf.name}:{len(tasks)}")
        passed = self.cand_pass if "candidate" in gguf.name else 0.5
        return EvalResult(float("nan"), 1.0, passed, {}, "sig")


def harness_task(tmp_path, name="python_a"):
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / f"{name}.toml").write_text('prompt = "p"\n', encoding="utf-8")


def run(tmp_path, spec, fakes, remaining=600.0, n_train=50):
    train, eval_ = data(tmp_path, n_train)
    return night.run_one(
        spec, tmp_path / "run", remaining, train_file=train, eval_file=eval_, models_dir=tmp_path / "models",
        baseline_dir=tmp_path / "baseline", tasks_dir=tmp_path / "tasks",
        train_fn=fakes.train, export_fn=fakes.export, eval_fn=fakes.evaluate,
    )  # fmt: skip


def test_a_specialist_is_trained_exported_evaluated_and_promoted(tmp_path):
    harness_task(tmp_path)
    (tmp_path / "tasks" / "python_a.toml").write_text('prompt = "p"\n', encoding="utf-8")
    fakes = Fakes()
    status = run(tmp_path, PY, fakes)
    assert status["status"] == "promoted", status
    assert (tmp_path / "models" / "specialists" / "python.gguf").read_bytes() == b"gguf"
    assert fakes.calls[:2] == ["train:python", "export"] and "eval:candidate-Q4_K_M.gguf:1" in fakes.calls
    assert run(tmp_path, PY, fakes) == status and fakes.calls.count("export") == 1  # resumed: nothing redone


def test_a_regressing_specialist_is_not_promoted(tmp_path):
    harness_task(tmp_path)
    status = run(tmp_path, PY, Fakes(cand_loss=1.2))
    assert status["status"] == "rejected" and "loss" in status["reason"]
    assert not (tmp_path / "models" / "specialists" / "python.gguf").exists()


def test_too_little_data_skips_the_specialist(tmp_path):
    harness_task(tmp_path)
    fakes = Fakes()
    status = run(tmp_path, GO, fakes)  # the data is all python: nothing for go
    assert status["status"] == "skipped" and not fakes.calls


def test_rotation_trains_the_never_trained_first_then_the_oldest():
    specialists = [PY, GO, Specialist("web", ["typescript"], ["ts"])]
    state = {"python": "2026-10-27", "go": "2026-10-26"}
    assert [s.name for s in night.rotation(specialists, state)] == ["web", "go", "python"]


def test_not_enough_time_left_stops_the_night(tmp_path):
    harness_task(tmp_path)
    fakes = Fakes()
    assert run(tmp_path, PY, fakes, remaining=night.RESERVE_MIN + 5)["status"] == "no time"
    assert not fakes.calls


def test_one_specialist_cannot_take_the_whole_night(tmp_path):
    harness_task(tmp_path)
    budgets = []
    fakes = Fakes()
    original = fakes.train
    fakes.train = lambda cfg, out_dir: budgets.append(cfg.time_budget_min) or original(cfg, out_dir)
    run(tmp_path, PY, fakes, remaining=1000.0)
    assert budgets == [night.MAX_TRAIN_MIN]


def test_a_failing_specialist_does_not_stop_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(night, "stop_llama_servers", lambda: None)
    web = Specialist("web", ["typescript"], ["ts"])

    def one(specialist, run_dir, remaining):
        if specialist.name == "python":
            raise RuntimeError("petru_train.train:train_from_json failed in a subprocess (exit code 1)")
        return {"status": "rejected", "name": specialist.name, "reason": "loss"}

    results = night.run_specialists("r", night.datetime(2030, 1, 1), [PY, web], runs_dir=tmp_path, one=one)
    assert [(r["name"], r["status"]) for r in results] == [("python", "failed"), ("web", "rejected")]
    assert "exit code 1" in results[0]["reason"]
    state = json.loads((tmp_path / "specialists.json").read_text(encoding="utf-8"))
    assert state == {"web": "r"}  # the failed one stays first in the rotation for the next night


def test_a_specialist_without_evaluation_tasks_is_not_trained(tmp_path):
    (tmp_path / "tasks").mkdir()
    fakes = Fakes()
    result = run(tmp_path, GO, fakes)
    assert result["status"] == "skipped" and "no evaluation tasks" in result["reason"] and not fakes.calls


def test_held_out_exercism_tasks_of_its_languages_evaluate_a_specialist(tmp_path, monkeypatch):
    from petru_train import evaluate
    from petru_train.exercism import held_out

    a, b, c = sorted(s for s in (f"s{i}" for i in range(300)) if held_out("", s))[:3]
    pool = tmp_path / "pool"
    manifest = {}
    for name in (f"go_ex_{a}", f"go_ex_{b}", f"rust_ex_{c}"):
        (pool / name).mkdir(parents=True)
        (pool / name / "task.toml").write_text('prompt = "p"\n', encoding="utf-8")
        manifest[name] = {"track": name.split("_")[0], "passed": True}
    (pool / "validated.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(evaluate, "EVAL_POOL", pool)
    (tmp_path / "tasks").mkdir()
    assert [t.parent.name for t in night.specialist_tasks(GO, tmp_path / "tasks")] == [
        f"go_ex_{a}",
        f"go_ex_{b}",
    ]


def test_baselines_of_seeded_tasks_are_cached_per_task_name(tmp_path):
    calls = []

    def eval_fn(gguf, tasks, log):
        calls.append([t.parent.name for t in tasks])
        return EvalResult(float("nan"), 1.0, 0.5, {}, "s")

    one, two = [tmp_path / "php_ex_a" / "task.toml"], [tmp_path / "ruby_ex_b" / "task.toml"]
    night._base_result(one, tmp_path / "baseline", eval_fn)
    night._base_result(two, tmp_path / "baseline", eval_fn)
    assert calls == [["php_ex_a"], ["ruby_ex_b"]]  # both are "task.toml": the stem would share one cache file
