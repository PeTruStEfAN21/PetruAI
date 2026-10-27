from petru import cli
from petru.config import Config, default_tiers
from tests.fakes import FakeProvider, call, result


class FakeManager:
    instances: list = []

    def __init__(self, cfg):
        self.cfg = cfg
        self.started: list[str] = []
        self.stopped = False
        FakeManager.instances.append(self)

    def ensure_running(self, tier):
        self.started.append(tier)
        return "http://127.0.0.1:8080/v1"

    def stop(self):
        self.stopped = True


def patch_runtime(monkeypatch, tmp_path, scripted):
    FakeManager.instances = []
    providers = []

    def make_provider(base_url):
        providers.append(FakeProvider(scripted))
        return providers[-1]

    monkeypatch.setattr(cli, "ServerManager", FakeManager)
    monkeypatch.setattr(cli, "make_provider", make_provider)
    monkeypatch.setattr(cli, "is_online", lambda: False)
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda root: Config(root, root / "models", root / "server.exe", tiers=default_tiers()),
    )
    return providers


def test_cli_parses_flags():
    ns = cli.build_parser().parse_args(["--model", "fast", "--yolo", "-p", "hi"])
    assert ns.model == "fast" and ns.yolo and ns.prompt == "hi"
    assert cli.build_parser().parse_args([]).model is None


def test_one_shot_runs_single_turn(tmp_path, monkeypatch, capsys):
    providers = patch_runtime(monkeypatch, tmp_path, [result(content="final text")])
    code = cli.main(["-p", "x", "--project", str(tmp_path), "--model", "fast"])
    assert code == 0
    assert "final text" in capsys.readouterr().out
    assert FakeManager.instances[0].started == ["fast"] and FakeManager.instances[0].stopped
    assert (tmp_path / ".git").is_dir()
    assert providers[0].calls[0]["messages"][-1] == {"role": "user", "content": "x"}
    assert "write_file" in [t["function"]["name"] for t in providers[0].calls[0]["tools"]]  # quick -> BUILD


def test_one_shot_exit_code_1_when_turn_hits_a_limit(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    limit = default_tiers()["default"].max_iterations
    patch_runtime(
        monkeypatch, tmp_path, [result(tool_calls=[call("read_file", {"path": "a.txt"})])] * (limit + 1)
    )
    assert cli.main(["-p", "x", "--project", str(tmp_path)]) == 1


def test_one_shot_declines_unknown_shell_unless_yolo(tmp_path, monkeypatch, capsys):
    providers = patch_runtime(
        monkeypatch,
        tmp_path,
        [result(tool_calls=[call("shell", {"command": "npm install zod"})]), result("ok")],
    )
    assert cli.main(["-p", "x", "--project", str(tmp_path)]) == 0
    assert providers[0].calls[1]["messages"][-1]["content"] == "User declined."


def test_server_start_error_is_reported(tmp_path, monkeypatch, capsys):
    patch_runtime(monkeypatch, tmp_path, [])

    def boom(self, tier):
        raise cli.ServerStartError("port busy")

    monkeypatch.setattr(FakeManager, "ensure_running", boom)
    assert cli.main(["-p", "x", "--project", str(tmp_path)]) == 2
    assert "port busy" in capsys.readouterr().err
