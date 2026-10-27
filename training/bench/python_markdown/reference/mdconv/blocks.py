"""Block structure: headings, paragraphs, lists, fenced code, rules and block quotes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HEADING = re.compile(r"^(#{1,6}) (.*)$")
BULLET = re.compile(r"^[-*] (.*)$")
NUMBERED = re.compile(r"^\d+\. (.*)$")
RULE = re.compile(r"^(---+|\*\*\*+)\s*$")
FENCE = re.compile(r"^```(\S*)\s*$")
QUOTE = re.compile(r"^> ?(.*)$")


@dataclass
class Block:
    kind: str  # heading, paragraph, ul, ol, code, hr, quote
    text: str = ""
    level: int = 0
    lang: str = ""
    items: list[str] = field(default_factory=list)
    children: list[Block] = field(default_factory=list)


def _starts_block(line: str) -> bool:
    return any(p.match(line) for p in (HEADING, BULLET, NUMBERED, RULE, FENCE, QUOTE))


def parse_blocks(text: str) -> list[Block]:
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if fence := FENCE.match(line):
            body = []
            i += 1
            while i < len(lines) and not FENCE.match(lines[i]):
                body.append(lines[i])
                i += 1
            blocks.append(Block("code", "\n".join(body), lang=fence.group(1)))
            i += 1  # the closing fence, if any
        elif heading := HEADING.match(line):
            blocks.append(Block("heading", heading.group(2).strip(), level=len(heading.group(1))))
            i += 1
        elif RULE.match(line):
            blocks.append(Block("hr"))
            i += 1
        elif QUOTE.match(line):
            inner = []
            while i < len(lines) and (quoted := QUOTE.match(lines[i])):
                inner.append(quoted.group(1))
                i += 1
            blocks.append(Block("quote", children=parse_blocks("\n".join(inner))))
        elif BULLET.match(line) or NUMBERED.match(line):
            pattern = BULLET if BULLET.match(line) else NUMBERED
            items = []
            while i < len(lines) and (item := pattern.match(lines[i])):
                items.append(item.group(1).strip())
                i += 1
            blocks.append(Block("ul" if pattern is BULLET else "ol", items=items))
        else:
            para = []
            while i < len(lines) and lines[i].strip() and (not para or not _starts_block(lines[i])):
                para.append(lines[i].strip())
                i += 1
            blocks.append(Block("paragraph", " ".join(para)))
    return blocks
