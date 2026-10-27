from __future__ import annotations

from mdconv.blocks import Block, parse_blocks
from mdconv.inline import escape, render_inline


def render_block(block: Block) -> str:
    if block.kind == "heading":
        return f"<h{block.level}>{render_inline(block.text)}</h{block.level}>"
    if block.kind == "paragraph":
        return f"<p>{render_inline(block.text)}</p>"
    if block.kind in ("ul", "ol"):
        items = "".join(f"<li>{render_inline(item)}</li>\n" for item in block.items)
        return f"<{block.kind}>\n{items}</{block.kind}>"
    if block.kind == "code":
        cls = f' class="language-{escape(block.lang)}"' if block.lang else ""
        return f"<pre><code{cls}>{escape(block.text)}</code></pre>"
    if block.kind == "hr":
        return "<hr>"
    if block.kind == "quote":
        return "<blockquote>\n" + render_blocks(block.children) + "\n</blockquote>"
    raise ValueError(f"unknown block {block.kind}")


def render_blocks(blocks: list[Block]) -> str:
    return "\n".join(render_block(b) for b in blocks)


def to_html(markdown: str) -> str:
    return render_blocks(parse_blocks(markdown))


def page(body: str, title: str) -> str:
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{escape(title)}</title>\n</head>\n<body>\n{body}\n</body>\n</html>"
    )
