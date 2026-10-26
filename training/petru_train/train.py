"""QLoRA SFT with Unsloth + TRL: assistant-only loss, checkpoints, automatic resume, time budget."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

TRAINING_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = TRAINING_DIR / "config" / "qlora-4b.toml"
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
INSTRUCTION_PART = "<|im_start|>user\n"
RESPONSE_PART = "<|im_start|>assistant\n"
NUMERIC_FIELDS = (
    "max_seq_len", "lora_r", "lora_alpha", "lora_dropout", "lr", "epochs", "batch_size", "grad_accum",
    "warmup_ratio", "weight_decay", "seed", "save_steps", "max_steps", "time_budget_min",
)  # fmt: skip


@dataclass
class TrainConfig:
    base_model: Path
    train_file: Path
    eval_file: Path
    out_dir: Path
    max_seq_len: int = 4096
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.0
    lr: float = 2e-4
    epochs: float = 1.0
    batch_size: int = 1
    grad_accum: int = 8
    warmup_ratio: float = 0.05
    weight_decay: float = 0.01
    seed: int = 3407
    save_steps: int = 50
    max_steps: int | None = None
    time_budget_min: int | None = None


def load_train_config(path: Path = DEFAULT_CONFIG, base_dir: Path | None = None) -> TrainConfig:
    base = base_dir or path.parent.parent
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    overrides = {key: data[key] for key in NUMERIC_FIELDS if key in data}
    return TrainConfig(
        base_model=(base / data["base_model"]).resolve(),
        train_file=base / data["train_file"],
        eval_file=base / data["eval_file"],
        out_dir=base / data.get("out_dir", "runs"),
        **overrides,
    )


@dataclass
class TrainReport:
    steps: int
    train_loss: float
    eval_loss: float
    minutes: float
    adapter_dir: str
    resumed_from: str | None


def latest_checkpoint(run_dir: Path) -> Path | None:
    best: tuple[int, Path] | None = None
    for candidate in run_dir.glob("checkpoint-*"):
        match = re.fullmatch(r"checkpoint-(\d+)", candidate.name)
        if match and candidate.is_dir() and (best is None or int(match.group(1)) > best[0]):
            best = (int(match.group(1)), candidate)
    return best[1] if best else None


class TimeBudgetCallback:
    """Stops training (after a checkpoint) once the wall-clock budget is spent. Duck-typed TrainerCallback."""

    def __init__(self, budget_min: int | None, clock: Callable[[], float] = time.monotonic) -> None:
        self.budget_s = budget_min * 60 if budget_min else None
        self.clock = clock
        self.started = clock()

    def on_step_end(self, args, state, control, **kwargs):
        if self.budget_s is not None and self.clock() - self.started > self.budget_s:
            control.should_training_stop = True
            control.should_save = True
        return control

    def __getattr__(self, name: str):  # every other TrainerCallback hook is a no-op
        if name.startswith("on_"):
            return lambda args, state, control, **kwargs: control
        raise AttributeError(name)


def train(cfg: TrainConfig, run_dir: Path) -> TrainReport:
    import torch
    from datasets import Dataset
    from transformers import TrainerCallback
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import train_on_responses_only

    from petru_train.samples import read_jsonl, render_chat, text_tokenizer

    class _Budget(TrainerCallback):
        def __init__(self, inner: TimeBudgetCallback) -> None:
            self.inner = inner

        def on_step_end(self, args, state, control, **kwargs):
            return self.inner.on_step_end(args, state, control, **kwargs)

    run_dir.mkdir(parents=True, exist_ok=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        str(cfg.base_model), max_seq_length=cfg.max_seq_len, load_in_4bit=True, dtype=None
    )
    tokenizer = text_tokenizer(tokenizer)  # the processor's text tokenizer; the model is trained on text only
    model = FastLanguageModel.get_peft_model(
        model,
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=TARGET_MODULES,
        use_gradient_checkpointing="unsloth",
        random_state=cfg.seed,
    )
    train_ds = Dataset.from_dict({"text": [render_chat(s, tokenizer) for s in read_jsonl(cfg.train_file)]})
    eval_ds = Dataset.from_dict({"text": [render_chat(s, tokenizer) for s in read_jsonl(cfg.eval_file)]})
    bf16 = bool(torch.cuda.is_bf16_supported())
    if cfg.max_steps is not None:
        total_steps = cfg.max_steps
    else:
        total_steps = math.ceil(len(train_ds) / (cfg.batch_size * cfg.grad_accum) * cfg.epochs)
    warmup_steps = max(0, int(cfg.warmup_ratio * total_steps))  # TRL >= 1.x only takes warmup_steps
    args = SFTConfig(
        output_dir=str(run_dir),
        per_device_train_batch_size=cfg.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=cfg.grad_accum,
        learning_rate=cfg.lr,
        num_train_epochs=cfg.epochs,
        max_steps=cfg.max_steps if cfg.max_steps is not None else -1,
        warmup_steps=warmup_steps,
        weight_decay=cfg.weight_decay,
        lr_scheduler_type="linear",
        optim="adamw_8bit",
        seed=cfg.seed,
        logging_steps=1,
        save_steps=cfg.save_steps,
        save_total_limit=3,
        bf16=bf16,
        fp16=not bf16,
        dataset_text_field="text",
        max_length=cfg.max_seq_len,
        packing=False,
        report_to="none",
        eval_strategy="no",
    )
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=args,
        callbacks=[_Budget(TimeBudgetCallback(cfg.time_budget_min))],
    )
    trainer = train_on_responses_only(trainer, instruction_part=INSTRUCTION_PART, response_part=RESPONSE_PART)
    checkpoint = latest_checkpoint(run_dir)
    started = time.monotonic()
    output = trainer.train(resume_from_checkpoint=str(checkpoint) if checkpoint else None)
    eval_loss = float(trainer.evaluate().get("eval_loss", float("nan")))
    adapter_dir = run_dir / "adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    report = TrainReport(
        steps=int(trainer.state.global_step),
        train_loss=float(output.training_loss),
        eval_loss=eval_loss,
        minutes=round((time.monotonic() - started) / 60, 2),
        adapter_dir=str(adapter_dir),
        resumed_from=checkpoint.name if checkpoint else None,
    )
    (run_dir / "train_report.json").write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QLoRA fine-tuning of the base model on the built dataset.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run", type=Path, required=True, help="run directory, e.g. runs/2026-10-27")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--time-budget-min", type=int, default=None)
    args = parser.parse_args(argv)
    cfg = load_train_config(args.config)
    if args.max_steps is not None:
        cfg.max_steps = args.max_steps
    if args.time_budget_min is not None:
        cfg.time_budget_min = args.time_budget_min
    report = train(cfg, args.run)
    print(json.dumps(asdict(report), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
