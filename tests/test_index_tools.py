import pytest

from petru import cli
from petru.agent.permissions import decide
from petru.agent.state import Phase, Session
from petru.config import Config, default_tiers
from petru.index import embed_server, tools
from petru.index.store import CodeIndex
from petru.tools.base import ToolContext
from petru.tools.registry import default_registry


@pytest.fixture(autouse=True)
def no_embed_server(tmp_path, monkeypatch):
    monkeypatch.setenv("PETRU_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(tools, "embedder_if_running", lambda: None)


def project(root):
    (root / "src").mkdir(parents=True)
    (root / "src" / "config.py").write_text("def parse_config(path):\n    return path\n", encoding="utf-8")
    (root / "README.md").write_text(
        "# Demo\n\nParses config files.\nSecond line.\nThird line.\n", encoding="utf-8"
    )
    return root


def test_search_code_refreshes_and_formats_hits(tmp_path):
    root = project(tmp_path / "p")
    out = tools.SearchCodeTool().run({"query": "parse_config"}, ToolContext(root, False)).output
    assert out.splitlines()[0] == "src/config.py:1-2 function parse_config"
    assert "def parse_config" in out and (root / ".petru" / "index.sqlite").is_file()
    (root / "src" / "new.py").write_text("def brand_new_thing():\n    pass\n", encoding="utf-8")
    assert (
        "src/new.py"
        in tools.SearchCodeTool().run({"query": "brand_new_thing"}, ToolContext(root, False)).output
    )


def test_search_code_no_hits(tmp_path):
    root = project(tmp_path / "p")
    assert tools.SearchCodeTool().run({"query": "zzzqqq"}, ToolContext(root, False)).output == "No matches."


def test_search_tools_registered_and_allowed_in_design(tmp_path):
    registry = default_registry(ctx_online=False)
    session = Session(tmp_path, phase=Phase.DESIGN)
    for name in ("search_code", "search_docs"):
        assert decide(registry.get(name), {"query": "x"}, session).kind == "allow"


def test_search_docs_explains_how_to_build_the_index(tmp_path):
    out = tools.SearchDocsTool().run({"query": "StatefulWidget"}, ToolContext(tmp_path, False)).output
    assert "petru index --docs" in out


def test_one_index_holds_several_roots_without_clobbering(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x.py").write_text("def alpha_fn():\n    pass\n", encoding="utf-8")
    (b / "y.py").write_text("def beta_fn():\n    pass\n", encoding="utf-8")
    index = CodeIndex(tmp_path / "docs.sqlite")
    index.update(a, prefix="flutter")
    index.update(b, prefix="website")
    index.update(a, prefix="flutter")
    paths = {h.path for h in index.search("alpha_fn beta_fn")}
    assert paths == {"flutter/x.py", "website/y.py"}


def test_cli_index_project_and_docs(tmp_path, monkeypatch, capsys):
    root = project(tmp_path / "p")
    assert cli.run_subcommand(["index", "--project", str(root), "--no-embed"]) == 0
    assert (root / ".petru" / "index.sqlite").is_file() and "chunks" in capsys.readouterr().out
    monkeypatch.setattr(tools, "docs_roots", lambda repo_root: {"demo": root / "src"})
    assert cli.run_subcommand(["index", "--docs", "--no-embed"]) == 0
    assert (tmp_path / "home" / "docs_index.sqlite").is_file()
    out = tools.SearchDocsTool().run({"query": "parse_config"}, ToolContext(tmp_path, False)).output
    assert out.startswith("demo/config.py:1-2")


def cfg(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    return Config(tmp_path, models, tmp_path / "llama-server.exe", tiers=default_tiers())


def test_embed_server_reused_when_healthy(tmp_path):
    spawned = []
    manager = embed_server.EmbedServer(
        cfg(tmp_path), spawn=lambda *a, **k: spawned.append(a), healthy=lambda: True
    )
    assert manager.ensure() == "http://127.0.0.1:8082/v1" and spawned == []


def test_embed_server_needs_the_model_file(tmp_path):
    manager = embed_server.EmbedServer(cfg(tmp_path), spawn=lambda *a, **k: None, healthy=lambda: False)
    assert manager.ensure() is None


def test_embed_server_starts_on_cpu(tmp_path):
    c = cfg(tmp_path)
    (c.models_dir / embed_server.EMBED_MODEL).write_bytes(b"gguf")
    state = {"up": False}
    spawned = []

    class Proc:
        def poll(self):
            return None

        def terminate(self):
            spawned.append("terminated")

        def wait(self, timeout=None):
            return 0

    def spawn(cmd, **kwargs):
        spawned.append(cmd)
        state["up"] = True
        return Proc()

    manager = embed_server.EmbedServer(c, spawn=spawn, healthy=lambda: state["up"], poll_s=0.01)
    assert manager.ensure() == "http://127.0.0.1:8082/v1"
    cmd = spawned[0]
    assert (
        "--embeddings" in cmd and cmd[cmd.index("-ngl") + 1] == "0" and cmd[cmd.index("--port") + 1] == "8082"
    )
    manager.stop()
    assert spawned[-1] == "terminated"
