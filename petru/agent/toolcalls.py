"""Turn model output into validated tool calls, repairing common small-model mistakes."""

from __future__ import annotations

import json
import re

from jsonschema import Draft202012Validator

from petru.providers.base import ChatResult, ToolCall

TAG_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_WHOLE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _try_load(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def repair_json(raw: str) -> dict | None:
    """Parse a JSON object, tolerating code fences, trailing commas and single quotes."""
    text = raw.strip()
    match = _WHOLE_FENCE_RE.match(text)
    if match:
        text = match.group(1)
    no_commas = _TRAILING_COMMA_RE.sub(r"\1", text)
    for candidate in (text, no_commas, no_commas.replace("'", '"')):
        parsed = _try_load(candidate)
        if parsed is not None:
            return parsed
    return None


def _call_from_object(obj: dict, index: int) -> ToolCall | None:
    name = obj.get("name")
    if not isinstance(name, str) or not name:
        return None
    args = obj.get("arguments", {})
    if args is None:
        args = {}
    if isinstance(args, str):
        parsed = repair_json(args) if args.strip() else {}
        raw = args
    elif isinstance(args, dict):
        parsed, raw = args, json.dumps(args)
    else:
        parsed, raw = None, json.dumps(args)
    return ToolCall(id=f"txt-{index}", name=name, arguments=parsed, raw_arguments=raw)


def _text_blocks(text: str) -> list[str]:
    blocks = TAG_RE.findall(text)
    return blocks if blocks else FENCE_RE.findall(text)


def extract_tool_calls(result: ChatResult) -> list[ToolCall]:
    """Native tool calls win; otherwise parse <tool_call> tags, then ```json fences."""
    if result.tool_calls:
        return list(result.tool_calls)
    calls: list[ToolCall] = []
    for block in _text_blocks(result.content or ""):
        obj = repair_json(block)
        if obj is None:
            continue
        call = _call_from_object(obj, len(calls) + 1)
        if call is not None:
            calls.append(call)
    return calls


def strip_text_tool_calls(text: str) -> str:
    """Remove tool-call blocks from text shown to the user; ordinary code fences stay."""
    stripped = TAG_RE.sub("", text)
    if stripped != text:
        return stripped

    def _drop_if_call(match: re.Match) -> str:
        obj = repair_json(match.group(1))
        return "" if obj is not None and "name" in obj and "arguments" in obj else match.group(0)

    return FENCE_RE.sub(_drop_if_call, text)


def validate_arguments(schema: dict, args: dict) -> list[str]:
    """Human-readable schema violations; empty when the arguments are valid."""
    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(args), key=lambda e: [str(p) for p in e.path]):
        where = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{where}: {err.message}")
    return errors
