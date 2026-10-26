"""Assemble the system prompt and keep the transcript inside the model's context window."""

from __future__ import annotations

import json
from pathlib import Path

from petru.agent.decisions import read_decisions
from petru.agent.prompts import (
    BASE_SYSTEM_PROMPT,
    BUILD_PHASE_PROMPT,
    DESIGN_PHASE_PROMPT,
    OFFLINE_RULES_PROMPT,
)
from petru.agent.state import Phase, Plan, Session
from petru.offline import load_offline_manifest
from petru.providers.base import ChatProvider

AGENTS_CAP_TOKENS = 2000
SUMMARY_PREFIX = "[Summary of earlier conversation]"
SUMMARIZE_INSTRUCTION = (
    "Summarize the conversation above for your own future reference: the task, the decisions, the files "
    "created or changed, what was verified, and what remains. Be specific and concise, under 300 words."
)


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def _tokens_of(messages: list[dict]) -> int:
    return estimate_tokens(json.dumps(messages, ensure_ascii=False))


def render_plan(plan: Plan) -> str:
    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(plan.steps, start=1))
    return f"## Confirmed plan: {plan.title}\n{steps}"


def build_system_prompt(session: Session, repo_root: Path, online: bool) -> str:
    parts = [BASE_SYSTEM_PROMPT, DESIGN_PHASE_PROMPT if session.phase is Phase.DESIGN else BUILD_PHASE_PROMPT]
    if session.plan is not None and session.plan.confirmed:
        parts.append(render_plan(session.plan))
    agents = session.project_root / "AGENTS.md"
    if agents.is_file():
        text = agents.read_text(encoding="utf-8", errors="replace")[: AGENTS_CAP_TOKENS * 4]
        parts.append(f"## Project instructions (AGENTS.md)\n{text}")
    decisions = read_decisions(session.project_root)
    if decisions:
        parts.append(f"## DECISIONS (final; the latest entry wins)\n{decisions}")
    if not online:
        manifest = load_offline_manifest(repo_root)
        listing = (
            "\n".join(f"- {eco}: {', '.join(pkgs)}" for eco, pkgs in manifest.items())
            or "- (no manifest found)"
        )
        parts.append(OFFLINE_RULES_PROMPT.format(packages=listing))
    return "\n\n".join(parts)


def transcript_tokens(messages: list[dict], provider: ChatProvider | None = None) -> int:
    """The provider's exact count (llama-server /tokenize) when it offers one, else the chars/4 estimate."""
    text = json.dumps(messages, ensure_ascii=False)
    counter = getattr(provider, "count_tokens", None)
    if counter is not None:
        counted = counter(text)
        if isinstance(counted, int):
            return counted
    return estimate_tokens(text)


def compact_if_needed(
    session: Session,
    provider: ChatProvider,
    ctx_tokens: int,
    reserve_tokens: int = 4096,
    keep_recent_tokens: int = 6000,
    force: bool = False,
) -> bool:
    """Summarize old messages when the transcript nears the context limit (or when forced after the server
    rejected the request as too long). Never splits a tool-call pair."""
    msgs = session.messages
    if not force and transcript_tokens(msgs, provider) <= ctx_tokens - reserve_tokens:
        return False
    start = 1 if msgs and msgs[0].get("role") == "system" else 0
    k, kept = len(msgs), 0
    while k > start + 1 and kept < keep_recent_tokens:
        k -= 1
        kept += estimate_tokens(json.dumps(msgs[k], ensure_ascii=False))
    while k > start and msgs[k].get("role") == "tool":
        k -= 1
    old = msgs[start:k]
    if not old:
        return False
    result = provider.complete(
        [*old, {"role": "user", "content": SUMMARIZE_INSTRUCTION}], None, max_tokens=1024
    )
    summary = result.content.strip() or "(no summary produced)"
    session.messages = [*msgs[:start], {"role": "user", "content": f"{SUMMARY_PREFIX}\n{summary}"}, *msgs[k:]]
    return True
