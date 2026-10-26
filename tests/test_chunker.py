import subprocess

from petru.index.chunker import Chunk, chunk_file, iter_project_files

PY = '''\
import os


class Store:
    """Keeps things."""

    def add(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)


def helper(x):
    return x * 2
'''

TS = """\
export const add = (a: number, b: number): number => a + b;

export class Notes {
  private items: string[] = [];

  list(): string[] {
    return this.items;
  }
}

interface Note { id: string }
"""

DART = """\
import 'package:flutter/material.dart';

class Counter extends StatelessWidget {
  const Counter({super.key});

  @override
  Widget build(BuildContext context) {
    return const Text('0');
  }
}

int twice(int x) {
  return x * 2;
}
"""


def names(chunks: list[Chunk]) -> list[tuple[str, str, int, int]]:
    return [(c.kind, c.name, c.start, c.end) for c in chunks if c.kind != "window"]


def test_python_class_methods_and_function():
    chunks = chunk_file("store.py", PY)
    assert ("class", "Store", 4, 11) in names(chunks)
    assert ("function", "add", 7, 8) in names(chunks) and ("function", "count", 10, 11) in names(chunks)
    assert ("function", "helper", 14, 15) in names(chunks)
    method = next(c for c in chunks if c.name == "add")
    assert method.text.startswith("    def add") and method.path == "store.py"


def test_typescript_arrow_const_class_method_and_interface():
    found = names(chunk_file("notes.ts", TS))
    assert ("function", "add", 1, 1) in found
    assert ("class", "Notes", 3, 9) in found and ("function", "list", 6, 8) in found
    assert ("type", "Note", 11, 11) in found


def test_dart_class_and_top_level_function():
    found = names(chunk_file("lib/main.dart", DART))
    assert any(kind == "class" and name == "Counter" for kind, name, _, _ in found)
    assert any(name == "twice" for _, name, _, _ in found)
    assert any(name == "build" for _, name, _, _ in found)


def test_unknown_extension_falls_back_to_overlapping_windows():
    text = "\n".join(f"line {i}" for i in range(1, 131)) + "\n"
    chunks = chunk_file("notes.txt", text)
    assert [(c.kind, c.start, c.end) for c in chunks] == [
        ("window", 1, 60),
        ("window", 51, 110),
        ("window", 101, 130),
    ]


def test_empty_and_whitespace_files_have_no_chunks():
    assert chunk_file("a.py", "") == [] and chunk_file("a.py", "\n\n  \n") == []


def test_module_code_outside_definitions_is_kept_as_a_window():
    text = "import os\nimport sys\nCONFIG = {\n  'a': 1,\n}\n\n\ndef f():\n    return 1\n"
    chunks = chunk_file("m.py", text)
    assert any(c.kind == "window" and c.start == 1 and "CONFIG" in c.text for c in chunks)


def test_iter_project_files_never_yields_secret_files(tmp_path):
    from petru.index.chunker import is_secret_file

    secrets = [".env", ".env.local", "id_rsa", "id_ed25519", "server.pem", "cert.key", "store.pfx"]
    for name in [*secrets, ".npmrc", "credentials.json", "secrets.toml"]:
        (tmp_path / name).write_text("SECRET=1\n", encoding="utf-8")
        assert is_secret_file(name), name
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "env.py").write_text("x = 2\n", encoding="utf-8")
    assert sorted(p.name for p in iter_project_files(tmp_path)) == ["app.py", "env.py"]


def test_iter_project_files_uses_git_and_skips_noise(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "node_modules" / "m").mkdir(parents=True)
    (tmp_path / "node_modules" / "m" / "i.js").write_text("1", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\x00\x01")
    (tmp_path / "big.txt").write_text("x" * 300_000, encoding="utf-8")
    (tmp_path / "ignored.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    walked = sorted(p.relative_to(tmp_path).as_posix() for p in iter_project_files(tmp_path))
    assert walked == [".gitignore", "ignored.py", "src/a.py"]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked = sorted(p.relative_to(tmp_path).as_posix() for p in iter_project_files(tmp_path))
    assert tracked == [".gitignore", "src/a.py"]  # git also drops what .gitignore lists
