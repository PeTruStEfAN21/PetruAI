"""Inline markup: code spans, links, strong and emphasis, with HTML escaping."""

from __future__ import annotations

import re

CODE = re.compile(r"`([^`]+)`")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
STRONG = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
EM = re.compile(r"(\*|_)(?=\S)(.+?)(?<=\S)\1")


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _emphasis(text: str) -> str:
    text = STRONG.sub(lambda m: f"<strong>{_emphasis(m.group(2))}</strong>", text)
    return EM.sub(lambda m: f"<em>{m.group(2)}</em>", text)


def render_inline(text: str) -> str:
    """Code spans and link targets are kept out of the emphasis pass through placeholders."""
    held: list[str] = []

    def hold(html: str) -> str:
        held.append(html)
        return f"\x00{len(held) - 1}\x00"

    text = CODE.sub(lambda m: hold(f"<code>{escape(m.group(1))}</code>"), text)
    text = LINK.sub(
        lambda m: hold(f'<a href="{escape(m.group(2))}">{_emphasis(escape(m.group(1)))}</a>'), text
    )
    text = _emphasis(escape(text))
    return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)
