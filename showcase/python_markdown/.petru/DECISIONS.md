# Decizii

Deciziile utilizatorului sunt finale. Intrările noi se adaugă la sfârșit; cea mai recentă câștigă.

- 2026-10-27: The spec says to split into modules: blocks, inline, render, cli. Should I create the package structure as mdconv/__init__.py, mdconv/blocks.py, mdconv/inline.py, mdconv/render.py, mdconv/cli.py? -> Keep to_html and main exactly as the tests use them; put blocks.py, inline.py, render.py and cli.py inside mdconv/.
- 2026-10-27: Package structure: mdconv/__init__.py, blocks.py, inline.py, render.py, cli.py
- 2026-10-27: to_html is the public API; cli.main(argv) is the CLI entry point
- 2026-10-27: Blocks module handles all block-level parsing; inline module handles text-level rendering
- 2026-10-27: render.py provides the full-page HTML template for --title flag
- 2026-10-27: Standard library only (re, sys, pathlib, argparse)
- 2026-10-27: plan confirmat: Markdown to HTML converter in Python 3 (6 pași)
