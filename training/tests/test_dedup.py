import json

from petru_train.dedup import balance_by_language, minhash_dedup
from petru_train.samples import Sample

WORDS = [f"word{i}" for i in range(300)]


def sample_with_content(sid: str, content: str, language: str = "python") -> Sample:
    return Sample(
        id=sid,
        source="commit",
        repo="r",
        license="MIT",
        commit="c",
        language=language,
        messages=[
            {"role": "user", "content": "task"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "w",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "a", "content": content}),
                        },
                    }
                ],
            },
        ],
        tools=[],
    )


def test_near_duplicates_keep_first_occurrence():
    base = " ".join(WORDS)
    near = " ".join(WORDS[:270] + [f"other{i}" for i in range(30)])
    different = " ".join(f"zzz{i}" for i in range(300))
    kept = minhash_dedup(
        [sample_with_content("a", base), sample_with_content("b", near), sample_with_content("c", different)]
    )
    assert [s.id for s in kept] == ["a", "c"]


def test_exact_duplicates_removed():
    kept = minhash_dedup([sample_with_content("a", "x " * 100), sample_with_content("b", "x " * 100)])
    assert [s.id for s in kept] == ["a"]


def test_balance_by_language_caps_the_dominant_language():
    samples = [sample_with_content(f"p{i}", f"py {i}") for i in range(80)]
    samples += [sample_with_content(f"d{i}", f"dart {i}", "dart") for i in range(20)]
    balanced = balance_by_language(samples, max_share=0.5, seed=42)
    languages = [s.language for s in balanced]
    assert languages.count("dart") == 20
    assert languages.count("python") <= 20
    assert [s.id for s in balance_by_language(samples, max_share=0.5, seed=42)] == [s.id for s in balanced]


def test_balance_leaves_already_balanced_sets_alone():
    samples = [sample_with_content(f"p{i}", f"py {i}") for i in range(10)]
    samples += [sample_with_content(f"d{i}", f"dart {i}", "dart") for i in range(10)]
    assert balance_by_language(samples, max_share=0.5) == samples
