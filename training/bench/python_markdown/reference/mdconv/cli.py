from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mdconv.render import page, to_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mdconv", description="Convert Markdown to HTML.")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--title", default=None, help="wrap the result in a full HTML page")
    args = parser.parse_args(argv)
    try:
        markdown = args.input.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"mdconv: cannot read {args.input}: {exc.strerror}", file=sys.stderr)
        return 1
    html = to_html(markdown)
    if args.title is not None:
        html = page(html, args.title)
    if args.output is None:
        sys.stdout.write(html + "\n")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(html + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
