import json
from pathlib import Path

import pytest

from petru_train.env import MODEL_DIR
from petru_train.samples import Sample, write_jsonl
from petru_train.train import TimeBudgetCallback, TrainConfig, latest_checkpoint, load_train_config

CONFIG_TOML = """\
base_model = "../infra/llama.cpp/models/hf/Qwen3.5-4B"
train_file = "data/train.jsonl"
eval_file = "data/eval.jsonl"
out_dir = "runs"
"""


def test_train_config_defaults_match_the_plan(tmp_path):
    path = tmp_path / "qlora-4b.toml"
    path.write_text(CONFIG_TOML, encoding="utf-8")
    cfg = load_train_config(path, base_dir=tmp_path)
    assert (
        cfg.base_model == (tmp_path / ".." / "infra" / "llama.cpp" / "models" / "hf" / "Qwen3.5-4B").resolve()
    )
    assert cfg.train_file == tmp_path / "data" / "train.jsonl" and cfg.out_dir == tmp_path / "runs"
    assert (cfg.max_seq_len, cfg.lora_r, cfg.lora_alpha, cfg.lora_dropout) == (4096, 16, 32, 0.0)
    assert (cfg.lr, cfg.epochs, cfg.batch_size, cfg.grad_accum) == (2e-4, 1.0, 1, 8)
    assert (cfg.warmup_ratio, cfg.weight_decay, cfg.seed, cfg.save_steps) == (0.05, 0.01, 3407, 50)
    assert cfg.max_steps is None and cfg.time_budget_min is None


def test_train_config_overrides(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text(
        CONFIG_TOML + "max_seq_len = 2048\nmax_steps = 20\ntime_budget_min = 90\n", encoding="utf-8"
    )
    cfg = load_train_config(path, base_dir=tmp_path)
    assert cfg.max_seq_len == 2048 and cfg.max_steps == 20 and cfg.time_budget_min == 90


def test_select_by_length_drops_samples_that_would_be_truncated():
    from petru_train.train import select_by_length

    kept, dropped = select_by_length(["a", "b", "c", "d"], [100, 4096, 4097, 9000], max_len=4096)
    assert kept == ["a", "b"] and dropped == 2


def test_latest_checkpoint_picks_the_highest_step(tmp_path):
    assert latest_checkpoint(tmp_path) is None
    for step in (50, 100, 7):
        (tmp_path / f"checkpoint-{step}").mkdir()
    (tmp_path / "checkpoint-bogus").mkdir()
    assert latest_checkpoint(tmp_path) == tmp_path / "checkpoint-100"


class FakeControl:
    should_training_stop = False
    should_save = False


def test_time_budget_callback_stops_and_saves_after_the_budget():
    clock = [0.0]
    callback = TimeBudgetCallback(budget_min=10, clock=lambda: clock[0])
    control = FakeControl()
    callback.on_step_end(None, None, control)
    assert not control.should_training_stop
    clock[0] = 11 * 60
    callback.on_step_end(None, None, control)
    assert control.should_training_stop and control.should_save


def test_time_budget_callback_without_budget_never_stops():
    control = FakeControl()
    TimeBudgetCallback(budget_min=None, clock=lambda: 1e9).on_step_end(None, None, control)
    assert not control.should_training_stop


def tiny_samples(n: int) -> list[Sample]:
    return [
        Sample(
            id=f"s{i}",
            source="commit",
            repo="r",
            license="MIT",
            commit="c",
            language="python",
            messages=[
                {"role": "user", "content": f"Write a function that returns {i}."},
                {"role": "assistant", "content": f"```python\ndef f():\n    return {i}\n```"},
            ],
            tools=[],
        )
        for i in range(n)
    ]


@pytest.mark.gpu
def test_train_two_steps_and_resume(tmp_path):
    from petru_train.train import train

    write_jsonl(tmp_path / "train.jsonl", tiny_samples(8))
    write_jsonl(tmp_path / "eval.jsonl", tiny_samples(2))
    cfg = TrainConfig(
        base_model=MODEL_DIR,
        train_file=tmp_path / "train.jsonl",
        eval_file=tmp_path / "eval.jsonl",
        out_dir=tmp_path / "runs",
        max_seq_len=1024,
        save_steps=1,
        max_steps=2,
    )
    run_dir = tmp_path / "runs" / "smoke"
    report = train(cfg, run_dir)
    assert report.steps == 2 and report.resumed_from is None
    assert (Path(report.adapter_dir) / "adapter_config.json").is_file()
    assert report.train_loss > 0 and report.eval_loss > 0 and report.minutes > 0
    assert json.loads((run_dir / "train_report.json").read_text(encoding="utf-8"))["steps"] == 2

    cfg.max_steps = 3
    report2 = train(cfg, run_dir)
    assert report2.resumed_from == "checkpoint-2" and report2.steps == 3
