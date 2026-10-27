from petru import cli
from petru.agent import team
from petru.config import Config, Tier, default_tiers
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


def patch_team(monkeypatch, tmp_path, lead_script, worker_script, tiers=None):
    patch_runtime(monkeypatch, tmp_path, [])
    scripts = [lead_script, worker_script]
    providers = []

    def make_provider(base_url):
        providers.append(FakeProvider(scripts[len(providers)]))
        return providers[-1]

    monkeypatch.setattr(cli, "make_provider", make_provider)
    if tiers is not None:
        monkeypatch.setattr(
            cli, "load_config", lambda root: Config(root, root / "models", root / "server.exe", tiers=tiers)
        )
    return providers


def test_team_mode_leads_with_the_quality_tier_and_starts_the_assistant_when_it_delegates(
    tmp_path, monkeypatch
):
    lead = [
        result(tool_calls=[call("choose_mode", {"mode": "team", "reason": "two files"})]),
        result(tool_calls=[call("delegate", {"task": "Write a.py with x = 1.", "files": ["a.py"]})]),
        result(content="done"),
    ]
    worker = [
        result(tool_calls=[call("write_file", {"path": "a.py", "content": "x = 1\n"})]),
        result(content="a.py written"),
    ]
    providers = patch_team(monkeypatch, tmp_path, lead, worker)
    assert cli.main(["-p", "x", "--project", str(tmp_path), "--team"]) == 0
    lead_manager, worker_manager = FakeManager.instances
    assert lead_manager.started == ["quality"] and worker_manager.started == ["fast"]
    assert worker_manager.cfg.port == lead_manager.cfg.port + team.WORKER_PORT_OFFSET
    assert lead_manager.stopped and worker_manager.stopped
    first = providers[0].calls[0]
    assert team.LEAD_PROMPT in first["messages"][0]["content"]
    assert {"delegate", "choose_mode"} <= {t["function"]["name"] for t in first["tools"]}
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_team_mode_starts_no_assistant_while_the_lead_works_alone(tmp_path, monkeypatch):
    patch_team(monkeypatch, tmp_path, [result(content="done")], [])
    assert cli.main(["-p", "x", "--project", str(tmp_path), "--team"]) == 0
    assert FakeManager.instances[1].started == [] and FakeManager.instances[1].stopped


def test_the_assistant_is_the_promoted_fine_tune_when_there_is_one(tmp_path, monkeypatch):
    tiers = {**default_tiers(), "tuned": Tier("tuned", "Qwen3.5-4B-petru.gguf", ctx=32768)}
    delegate = call("delegate", {"task": "Write a.py.", "files": ["a.py"]})
    patch_team(
        monkeypatch,
        tmp_path,
        [result(tool_calls=[delegate]), result(content="done")],
        [result(content="ok")],
        tiers=tiers,
    )
    cli.main(["-p", "x", "--project", str(tmp_path), "--team"])
    assert FakeManager.instances[1].started == ["tuned"]


def test_each_new_task_in_the_repl_lets_the_lead_choose_again(tmp_path):
    from petru.agent.loop import Agent
    from petru.agent.state import Session
    from petru.tools.registry import default_registry

    registry = default_registry(False)
    team.lead_registry(registry, team.Worker(provider=lambda tier: None, ctx_tokens=8192))
    registry.get("choose_mode").mode = "solo"  # what the lead chose for the previous task
    session = Session(tmp_path, role=team.LEAD_PROMPT)
    ui = cli.NonInteractiveUI(cli.Console(), yolo=True)
    agent = Agent(FakeProvider([result(content="hi")]), registry, ui, session, tmp_path, 8192, False)
    cli._run_turn(agent, ui, cli.Console(), "next task")
    assert registry.get("choose_mode").mode is None


def test_a_piece_goes_to_its_language_specialist_when_one_was_promoted(tmp_path, monkeypatch):
    tiers = {**default_tiers(), "tuned-python": Tier("tuned-python", "specialists/python.gguf", ctx=32768)}
    delegate = call("delegate", {"task": "Write a.py.", "files": ["a.py"]})
    lead = [result(tool_calls=[delegate]), result(content="done")]
    patch_team(monkeypatch, tmp_path, lead, [result(content="ok")], tiers=tiers)
    cli.main(["-p", "x", "--project", str(tmp_path), "--team"])
    assert FakeManager.instances[1].started == ["tuned-python"]
