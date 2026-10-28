# python_markdown

Built by the PetruAI team: Qwen3.6-35B-A3B leading, Qwen3.5-4B assisting, both run locally.

## Task

Build a Markdown to HTML converter in Python 3 (standard library only), as the package `mdconv/` at the project root. The acceptance tests are tests/test_convert.py and tests/test_cli.py; do not change them or pyproject.toml.

API: `mdconv.to_html(markdown: str) -> str`, and `mdconv.cli.main(argv) -> int`.

Blocks (rendered blocks are joined with a single "\n", no trailing newline; blank lines separate blocks):
- `#` to `######` followed by a space: <h1>..<h6>, text stripped. Anything else starting with # is a paragraph.
- Paragraph: consecutive non-blank lines joined with one space, <p>...</p>. A line that starts another block ends the paragraph.
- `- ` or `* ` items: <ul>, `1. ` style items: <ol>; rendered as "<ul>\n<li>a</li>\n<li>b</li>\n</ul>". Switching between bullet and number starts a new list.
- Fenced code: ``` with an optional language, until the closing ``` or the end of the text: <pre><code class="language-py">...</code></pre> (no class without a language); content escaped, lines kept.
- `---` or `***` alone: <hr>.
- `> ` lines: <blockquote>\n(inner blocks, parsed recursively)\n</blockquote>.

Inline (in headings, paragraphs and list items): escape & < > " first; `code` is literal (escaped, no other markup); [text](url) -> <a href="url">text</a>; **x** or __x__ -> <strong>; *x* or _x_ -> <em> (the marker must touch non-space text on both sides, so "2 * 3" stays as is).

CLI: main([input, "-o", output, "--title", title]): reads the input file, writes the HTML plus a newline to the output file (parent folders created) or to stdout; with --title it wraps the body in a full page (see the test). A missing input prints an error naming the file to stderr and returns 1.

Split the code into modules: blocks (block parser), inline, render, cli.

## Result

- Acceptance tests: failed
- Time: 60 min as a team, 12 min for the 35B alone
- Pieces handed to the assistant: 0

## Who wrote what

| File | Written by |
|---|---|
| `.petru/DECISIONS.md` | lead |
| `mdconv/__init__.py` | lead |
| `mdconv/blocks.py` | lead |
| `mdconv/cli.py` | lead |
| `mdconv/inline.py` | lead |
| `mdconv/render.py` | lead |
| `pyproject.toml` | given with the task |
| `tests/test_cli.py` | given with the task |
| `tests/test_convert.py` | given with the task |
