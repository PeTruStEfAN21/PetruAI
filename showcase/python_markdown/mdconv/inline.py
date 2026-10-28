"""Inline Markdown rendering."""
import re


def escape(text: str) -> str:
    """Escape HTML special characters."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text


def render_inline(text: str) -> str:
    """Render inline Markdown elements.

    Order matters: code spans first (to protect their contents),
    then links, then strong/emphasis.
    """
    # 1. Code spans: `...` — escape content, no other markup
    result = _render_code_spans(text)
    # 2. Links: [text](url)
    result = _render_links(result)
    # 3. Strong: **text** or __text__
    result = _render_strong(result)
    # 4. Emphasis: *text* or _text_
    result = _render_emphasis(result)
    return result


def _render_code_spans(text: str) -> str:
    """Replace `code` with <code>escaped_code</code>."""
    parts = []
    last_end = 0
    for m in re.finditer(r'`([^`]+?)`', text):
        parts.append(escape(text[last_end:m.start()]))
        parts.append("<code>")
        parts.append(escape(m.group(1)))
        parts.append("</code>")
        last_end = m.end()
    parts.append(escape(text[last_end:]))
    return "".join(parts)


def _render_links(text: str) -> str:
    """Replace [text](url) with <a href="url">text</a>.

    The text inside is rendered recursively (for nested inline like **bold**).
    """
    def repl(m):
        link_text = render_inline(m.group(1))
        url = escape(m.group(2))
        return f'<a href="{url}">{link_text}</a>'
    return re.sub(r'\[([^\]]*?)\]\(([^)]*?)\)', repl, text)


def _render_strong(text: str) -> str:
    """Replace **text** or __text__ with <strong>text</strong>.

    Markers must touch non-space text on both sides.
    """
    # **text**
    def repl(m):
        inner = m.group(1)
        # Check: marker must touch non-space text on both sides
        start = m.start()
        end = m.end()
        before_ok = start == 0 or not text[start - 1].isspace()
        after_ok = end == len(text) or not text[end].isspace()
        if before_ok and after_ok:
            return f"<strong>{inner}</strong>"
        return m.group(0)
    text = re.sub(r'\*\*(.+?)\*\*', repl, text)
    # __text__
    def repl2(m):
        inner = m.group(1)
        start = m.start()
        end = m.end()
        before_ok = start == 0 or not text[start - 1].isspace()
        after_ok = end == len(text) or not text[end].isspace()
        if before_ok and after_ok:
            return f"<strong>{inner}</strong>"
        return m.group(0)
    text = re.sub(r'__(.+?)__', repl2, text)
    return text


def _render_emphasis(text: str) -> str:
    """Replace *text* or _text_ with <em>text</em>.

    Markers must touch non-space text on both sides.
    """
    # *text*
    def repl(m):
        inner = m.group(1)
        start = m.start()
        end = m.end()
        before_ok = start == 0 or not text[start - 1].isspace()
        after_ok = end == len(text) or not text[end].isspace()
        if before_ok and after_ok:
            return f"<em>{inner}</em>"
        return m.group(0)
    text = re.sub(r'\*(.+?)\*', repl, text)
    # _text_
    def repl2(m):
        inner = m.group(1)
        start = m.start()
        end = m.end()
        before_ok = start == 0 or not text[start - 1].isspace()
        after_ok = end == len(text) or not text[end].isspace()
        if before_ok and after_ok:
            return f"<em>{inner}</em>"
        return m.group(0)
    text = re.sub(r'_(.+?)_', repl2, text)
    return text
