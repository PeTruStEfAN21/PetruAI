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


def run(tmp_path, spec, fakes, remaining=600.0, n_train=50):
    train, eval_ = data(tmp_path, n_train)
    return night.run_one(
        spec, tmp_path / "run", remaining, train_file=train, eval_file=eval_, models_dir=tmp_path / "models",
        baseline_dir=tmp_path / "baseline", tasks_dir=tmp_path / "tasks",
        train_fn=fakes.train, export_fn=fakes.export, eval_fn=fakes.evaluate,
    )  # fmt: skip


def test_a_specialist_is_trained_exported_evaluated_and_promoted(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "python_a.toml").write_text('prompt = "p"\n', encoding="utf-8")
    fakes = Fakes()
    status = run(tmp_path, PY, fakes)
    assert status["status"] == "promoted", status
    assert (tmp_path / "models" / "specialists" / "python.gguf").read_bytes() == b"gguf"
    assert fakes.calls[:2] == ["train:python", "export"] and "eval:candidate-Q4_K_M.gguf:1" in fakes.calls
    assert run(tmp_path, PY, fakes) == status and fakes.calls.count("export") == 1  # resumed: nothing redone


def test_a_regressing_specialist_is_not_promoted(tmp_path):
    (tmp_path / "tasks").mkdir()
    status = run(tmp_path, PY, Fakes(cand_loss=1.2))
    assert status["status"] == "rejected" and "loss" in status["reason"]
    assert not (tmp_path / "models" / "specialists" / "python.gguf").exists()


def test_too_little_data_skips_the_specialist(tmp_path):
    (tmp_path / "tasks").mkdir()
    fakes = Fakes()
    status = run(tmp_path, GO, fakes)  # the data is all python: nothing for go
    assert status["status"] == "skipped" and not fakes.calls


def test_rotation_trains_the_never_trained_first_then_the_oldest():
    specialists = [PY, GO, Specialist("web", ["typescript"], ["ts"])]
    state = {"python": "2026-10-27", "go": "2026-10-26"}
    assert [s.name for s in night.rotation(specialists, state)] == ["web", "go", "python"]


def test_not_enough_time_left_stops_the_night(tmp_path):
    (tmp_path / "tasks").mkdir()
    fakes = Fakes()
    assert run(tmp_path, PY, fakes, remaining=night.RESERVE_MIN + 5)["status"] == "no time"
    assert not fakes.calls
