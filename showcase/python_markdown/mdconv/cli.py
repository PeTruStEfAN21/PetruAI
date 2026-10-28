"""CLI entry point for mdconv."""
import sys
from pathlib import Path
from mdconv import to_html
from mdconv.render import render_page


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, convert markdown to HTML, write output.

    Returns 0 on success, 1 on error.
    """
    if argv is None:
        argv = sys.argv[1:]

    # Simple argument parsing
    input_file = None
    output_file = None
    title = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "-o":
            i += 1
            if i < len(argv):
                output_file = argv[i]
        elif arg == "--title":
            i += 1
            if i < len(argv):
                title = argv[i]
        else:
            if input_file is None:
                input_file = arg
        i += 1

    if input_file is None:
        print("Error: no input file specified", file=sys.stderr)
        return 1

    path = Path(input_file)
    if not path.exists():
        print(f"Error: file not found: {input_file}", file=sys.stderr)
        return 1

    markdown = path.read_text(encoding="utf-8")
    html = to_html(markdown)

    if title is not None:
        html = render_page(html, title)
    else:
        html = html + "\n" if html else ""

    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
    else:
        if html:
            print(html)

    return 0
