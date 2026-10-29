"""The full-screen view's side panel and top bar, as plain data: what they show and what can be clicked."""

import subprocess

from petru.agent.state import Phase, Plan
from petru.app import App
from petru.cli import TeamModes
from petru.config import Config, default_tiers
from petru.tui.panel import changed_files, panel_sections
from petru.tui.port import ScriptedUI
from petru.tui.toolbar import model_choices, toolbar_items
from tests.fakes import FakeProvider, make_agent
from tests.test_cli import FakeManager


def make_app(tmp_path):
    cfg = Config(tmp_path, tmp_path / "models", tmp_path / "server.exe", tiers=default_tiers())
    agent = make_agent(FakeProvider([]), ScriptedUI(), tmp_path)
    return App(agent, FakeManager(cfg), cfg, TeamModes(cfg, tmp_path, False), False, say=lambda text: None)


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_changed_files_mark_new_modified_and_deleted(tmp_path):
    git(tmp_path, "init", "-q")
    for name in ("b.py", "c.py"):
        (tmp_path / name).write_text("x\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    (tmp_path / "a.py").write_text("new\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("changed\n", encoding="utf-8")
    (tmp_path / "c.py").unlink()
    assert changed_files(tmp_path) == ["+ a.py", "~ b.py", "- c.py"]
    assert changed_files(tmp_path, limit=2) == ["+ a.py", "~ b.py", "… 1 more"]
    assert changed_files(tmp_path / "missing") == []


def test_team_and_model_are_greyed_during_a_task(tmp_path):
    app = make_app(tmp_path)
    assert all(item.enabled for item in toolbar_items(app))
    app.session.phase = Phase.DESIGN
    enabled = {item.key: item.enabled for item in toolbar_items(app)}
    assert enabled == {"model": False, "team": False, "think": True, "yolo": True, "panel": True}
    app.session.phase, app.busy = Phase.IDLE, True
    assert {item.key: item.enabled for item in toolbar_items(app)}["model"] is False


def test_the_bar_names_the_tier_and_the_switches(tmp_path):
    app = make_app(tmp_path)
    app.session.yolo = True
    labels = [item.label for item in toolbar_items(app)]
    assert labels == ["Model: default ▾", "Team: off", "Think: off", "Yolo: on", "Panel"]


def test_model_choices_list_existing_tiers_plus_auto(tmp_path):
    cfg = Config(tmp_path, tmp_path, tmp_path / "s.exe", tiers=default_tiers())
    cfg.tiers["tuned-python"] = cfg.tiers["fast"]
    cfg.tiers["tuned"] = cfg.tiers["fast"]
    assert model_choices(cfg) == ["fast", "default", "quality", "auto", "tuned", "tuned-python"]


def test_panel_shows_plan_team_and_model(tmp_path):
    app = make_app(tmp_path)
    app.session.plan = Plan("Todo", ["a", "b"])
    app.agent.usage.record(4096, 100, 4.0, 1)
    sections = dict(panel_sections(app, ["+ a.py"]))
    assert list(sections) == ["Plan", "Files", "Team", "Model"]
    assert sections["Plan"] == ["1. a", "2. b"] and sections["Files"] == ["+ a.py"]
    assert sections["Team"] == ["off"]
    assert sections["Model"] == ["default · context 25% · 25 tok/s"]
    app.session.plan = None
    assert dict(panel_sections(app, []))["Plan"] == ["no plan yet"]
