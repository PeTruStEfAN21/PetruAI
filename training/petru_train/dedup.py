"""Near-duplicate removal (MinHash over the written code) and language balancing."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict

from datasketch import MinHash, MinHashLSH

from petru_train.samples import Sample


def written_text(sample: Sample) -> str:
    """Everything the assistant wrote or edited in the trajectory; falls back to all assistant text."""
    parts: list[str] = []
    for message in sample.messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            if function.get("name") in ("write_file", "edit_file"):
                try:
                    args = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    continue
                parts.append(str(args.get("content") or args.get("new") or ""))
    if not parts:
        parts = [str(m.get("content") or "") for m in sample.messages if m.get("role") == "assistant"]
    return "\n".join(parts)


def _shingles(text: str, ngram: int) -> set[str]:
    words = text.split()
    if len(words) < ngram:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + ngram]) for i in range(len(words) - ngram + 1)}


def minhash_dedup(
    samples: list[Sample], threshold: float = 0.7, ngram: int = 5, num_perm: int = 128
) -> list[Sample]:
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    kept: list[Sample] = []
    for index, sample in enumerate(samples):
        minhash = MinHash(num_perm=num_perm)
        for shingle in _shingles(written_text(sample), ngram):
            minhash.update(shingle.encode("utf-8"))
        if lsh.query(minhash):
            continue
        lsh.insert(str(index), minhash)
        kept.append(sample)
    return kept


def balance_by_language(samples: list[Sample], max_share: float = 0.4, seed: int = 42) -> list[Sample]:
    """Downsample any language above `max_share` of the final total; order is preserved.

    A language is capped relative to the others (n <= share/(1-share) * rest), so a single-language
    set is left alone. Two passes settle the rare case of several languages over the share at once."""
    rng = random.Random(seed)
    by_language: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_language[sample.language].append(sample)
    if len(by_language) < 2 or not 0 < max_share < 1:
        return list(samples)
    ratio = max_share / (1 - max_share)
    dropped: set[str] = set()
    for _ in range(3):
        counts = Counter({lang: len(group) for lang, group in by_language.items()})
        total = sum(counts.values())
        changed = False
        for language in sorted(counts):
            cap = max(1, int(ratio * (total - counts[language])))
            if counts[language] > cap:
                ids = sorted(s.id for s in by_language[language])
                extra = set(rng.sample(ids, counts[language] - cap))
                dropped |= extra
                by_language[language] = [s for s in by_language[language] if s.id not in extra]
                changed = True
        if not changed:
            break
    return [s for s in samples if s.id not in dropped]
