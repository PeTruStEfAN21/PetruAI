"""Block-level Markdown parsing."""
import re
from mdconv.inline import render_inline


def parse_blocks(text: str) -> list:
    """Parse Markdown text into a list of block strings (already rendered HTML)."""
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue
        # Fenced code block
        if line.strip().startswith("```"):
            lang_match = re.match(r'^```(\s*)(.*?)$', line.strip())
            lang = lang_match.group(2).strip() if lang_match else ""
            code_lines = []
            i += 1
            while i < len(lines):
                if lines[i].strip() == "```":
                    i += 1
                    break
                code_lines.append(lines[i])
            escaped = "\n".join(code_lines)
            if lang:
                blocks.append(f'<pre><code class="language-{_escape_attr(lang)}">{escaped}</code></pre>')
            else:
                blocks.append(f'<pre><code>{escaped}</code></pre>')
            continue
        # Heading
        heading_match = re.match(r'^(#{1,6})\s+(.*?)(?:\s*)?$', line)
        if heading_match:
            level = len(heading_match.group(1))
            content = heading_match.group(2).rstrip()
            blocks.append(f"<h{level}>{render_inline(content)}</h{level}>")
            i += 1
            continue
        # Horizontal rule
        stripped = line.strip()
        if len(stripped) >= 3 and all(c in '-*' for c in stripped) and stripped.replace('-', '').replace('*', '').replace(' ', '') == '':
            blocks.append("<hr>")
            i += 1
            continue
        # Blockquote
        if line.startswith("> "):
            bq_lines = []
            while i < len(lines) and (lines[i].startswith("> ") or lines[i].startswith(">")):
                if lines[i].startswith("> "):
                    bq_lines.append(lines[i][2:])
                elif lines[i] == ">":
                    bq_lines.append("")
                i += 1
            inner_text = "\n".join(bq_lines)
            inner_blocks = parse_blocks(inner_text)
            blocks.append("<blockquote>\n" + "\n".join(inner_blocks) + "\n</blockquote>")
            continue
        # Unordered list
        if re.match(r'^[\-\*]\s+', line):
            items = []
            while i < len(lines) and re.match(r'^[\-\*]\s+', lines[i]):
                item_text = re.sub(r'^[\-\*]\s+', '', lines[i])
                items.append(f"<li>{render_inline(item_text)}</li>")
                i += 1
            blocks.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue
        # Ordered list
        if re.match(r'^\d+\.\s+', line):
            items = []
            while i < len(lines) and re.match(r'^\d+\.\s+', lines[i]):
                item_text = re.sub(r'^\d+\.\s+', '', lines[i])
                items.append(f"<li>{render_inline(item_text)}</li>")
                i += 1
            blocks.append("<ol>\n" + "\n".join(items) + "\n</ol>")
            continue
        # Paragraph
        para_lines = []
        while i < len(lines):
            cur = lines[i]
            if cur.strip() == "":
                break
            if re.match(r'^#{1,6}\s+', cur):
                break
            if cur.strip().startswith("```"):
                break
            cur_stripped = cur.strip()
            if len(cur_stripped) >= 3 and all(c in '-*' for c in cur_stripped) and cur_stripped.replace('-', '').replace('*', '').replace(' ', '') == '':
                break
            if cur.startswith("> "):
                break
            if re.match(r'^[\-\*]\s+', cur):
                break
            if re.match(r'^\d+\.\s+', cur):
                break
            para_lines.append(cur)
            i += 1
        if para_lines:
            content = " ".join(para_lines)
            blocks.append(f"<p>{render_inline(content)}</p>")
    return blocks


def _escape_attr(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def to_html(markdown: str) -> str:
    if not markdown.strip():
        return ""
    blocks = parse_blocks(markdown)
    return "\n".join(blocks)
