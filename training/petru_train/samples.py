"""The one record every builder produces and every consumer reads: a chat transcript with the petru tools."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

SCHEMAS_FILE = Path(__file__).resolve().parents[1] / "schemas" / "tools.json"
Source = Literal["commit", "trajectory", "repo_file"]


@dataclass
class Sample:
    id: str
    source: Source
    repo: str
    license: str
    commit: str
    language: str
    messages: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)


def load_tools(path: Path = SCHEMAS_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, samples: Iterable[Sample]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for sample in samples:
            fh.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[Sample]:
    samples = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                samples.append(Sample(**json.loads(line)))
    return samples


def split(
    samples: list[Sample], eval_frac: float = 0.05, seed: int = 42
) -> tuple[list[Sample], list[Sample]]:
    """Stratified by language: every language with >= 20 samples gives at least one to eval."""
    rng = random.Random(seed)
    by_language: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_language[sample.language].append(sample)
    eval_ids: set[str] = set()
    for language in sorted(by_language):
        group = sorted(by_language[language], key=lambda s: s.id)
        n_eval = round(len(group) * eval_frac)
        if len(group) >= 20:
            n_eval = max(1, n_eval)
        eval_ids.update(s.id for s in rng.sample(group, n_eval))
    train = [s for s in samples if s.id not in eval_ids]
    eval_ = [s for s in samples if s.id in eval_ids]
    return train, eval_


def _template_messages(messages: list[dict]) -> list[dict]:
    """Qwen templates want tool-call arguments as a mapping; the transcript stores the OpenAI JSON string."""
    out = []
    for message in messages:
        if message.get("tool_calls"):
            message = json.loads(json.dumps(message))
            for call in message["tool_calls"]:
                args = call.get("function", {}).get("arguments")
                if isinstance(args, str):
                    try:
                        call["function"]["arguments"] = json.loads(args)
                    except json.JSONDecodeError:
                        pass
        out.append(message)
    return out


def text_tokenizer(tokenizer: Any) -> Any:
    """The text tokenizer behind a multimodal processor (Unsloth returns a Qwen3VLProcessor for Qwen3.5)."""
    return getattr(tokenizer, "tokenizer", tokenizer)


def render_chat(sample: Sample, tokenizer: Any) -> str:
    return text_tokenizer(tokenizer).apply_chat_template(
        _template_messages(sample.messages),
        tools=sample.tools or None,
        tokenize=False,
        enable_thinking=False,
    )


def count_tokens(sample: Sample, tokenizer: Any) -> int:
    encoded = text_tokenizer(tokenizer)(render_chat(sample, tokenizer), add_special_tokens=False)
    return len(encoded["input_ids"])
