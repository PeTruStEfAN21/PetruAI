import json

import pytest

from petru_train.env import MODEL_DIR
from petru_train.samples import Sample, load_tools, read_jsonl, render_chat, split, write_jsonl


def sample(i: int, language: str = "python") -> Sample:
    return Sample(
        id=f"s{i}",
        source="commit",
        repo="demo",
        license="MIT",
        commit="abc123",
        language=language,
        messages=[
            {"role": "user", "content": f"task {i}"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "a.py", "content": "x"}),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Wrote a.py"},
            {"role": "assistant", "content": "done"},
        ],
        tools=load_tools(),
    )


def test_load_tools_reads_committed_schemas():
    tools = load_tools()
    assert tools and tools[0]["type"] == "function" and tools[0]["function"]["name"] == "read_file"


def test_jsonl_round_trip(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [sample(1), sample(2, "dart")])
    back = read_jsonl(path)
    assert back == [sample(1), sample(2, "dart")]
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_write_jsonl_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [sample(1)])
    newer = [sample(2), sample(3)]  # built before json.dumps is broken below

    def broken(*args, **kwargs):
        raise KeyboardInterrupt  # the night is stopped in the middle of a write

    import json as json_module

    monkeypatch.setattr(json_module, "dumps", broken)
    try:
        write_jsonl(path, newer)
    except KeyboardInterrupt:
        pass
    monkeypatch.undo()
    assert read_jsonl(path) == [sample(1)]  # the old complete file survives
    assert [p.name for p in tmp_path.iterdir()] == ["s.jsonl"]


def test_split_is_stratified_and_deterministic():
    samples = [sample(i) for i in range(100)] + [sample(100 + i, "dart") for i in range(30)]
    train, eval_ = split(samples, eval_frac=0.05, seed=42)
    assert len(train) + len(eval_) == 130
    assert sum(s.language == "python" for s in eval_) == 5
    assert sum(s.language == "dart" for s in eval_) == 2
    assert [s.id for s in split(samples, eval_frac=0.05, seed=42)[1]] == [s.id for s in eval_]
    assert not {s.id for s in train} & {s.id for s in eval_}


def test_split_small_language_still_gets_one_eval_sample():
    samples = [sample(i) for i in range(100)] + [sample(200 + i, "sql") for i in range(20)]
    _, eval_ = split(samples, eval_frac=0.01, seed=1)
    assert sum(s.language == "sql" for s in eval_) == 1


@pytest.mark.skipif(not MODEL_DIR.is_dir(), reason="base model tokenizer not downloaded")
def test_render_chat_with_real_tokenizer():
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    text = render_chat(sample(1), tokenizer)
    assert "<tool_call>" in text and "write_file" in text
    assert "<think>\n\n</think>" in text  # thinking disabled renders an empty think block
    assert "task 1" in text and "done" in text
