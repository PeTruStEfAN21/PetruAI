"""The `petru` command: start the local model server, then a REPL or a one-shot prompt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from petru.agent.loop import Agent
from petru.agent.state import Session
from petru.config import find_repo_root, load_config
from petru.memory.tools import memory_prompt_section
from petru.offline import is_online
from petru.providers.openai_compat import OpenAICompatProvider
from petru.server import ServerManager, ServerStartError
from petru.tools.git import ensure_repo
from petru.tools.registry import default_registry
from petru.tui.commands import HELP_TEXT, parse_command
from petru.tui.rich_ui import NonInteractiveUI, RichUI

TIERS = ("default", "quality", "fast", "tuned")


def make_provider(base_url: str) -> OpenAICompatProvider:
    return OpenAICompatProvider(base_url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="petru", description="Local coding agent in your terminal.")
    parser.add_argument("--model", choices=TIERS, default=None, help="model tier (default from config)")
    parser.add_argument("--yolo", action="store_true", help="never ask for confirmation; build immediately")
    parser.add_argument("--project", default=".", help="project directory (default: current directory)")
    parser.add_argument("-p", "--prompt", default=None, help="run one prompt non-interactively and exit")
    return parser


def _status(session: Session, online: bool) -> str:
    return (
        f"phase={session.phase.value} tier={session.tier} project={session.project_root} "
        f"{'online' if online else 'offline'}{' yolo' if session.yolo else ''}"
    )


def _switch_model(manager: ServerManager, agent: Agent, cfg, tier: str, console: Console) -> None:
    if tier not in cfg.tiers:
        console.print(f"Unknown tier {tier!r}. Tiers: {', '.join(cfg.tiers)}", markup=False)
        return
    try:
        manager.ensure_running(tier)
    except ServerStartError as exc:
        console.print(f"[red]{exc}[/]", markup=True, highlight=False)
        return
    agent.session.tier = tier
    agent.ctx_tokens = cfg.tiers[tier].ctx
    console.print(f"Model tier: {tier} ({cfg.tiers[tier].model_file})", markup=False)


def _run_turn(agent: Agent, ui: RichUI, console: Console, text: str, quick: bool = False) -> None:
    try:
        agent.run_turn(text, quick=quick)
    except KeyboardInterrupt:
        console.print("[yellow]Turn cancelled.[/]", markup=True)
    except Exception as exc:  # the REPL survives a provider/tool crash; the error is shown
        console.print(f"[red]{type(exc).__name__}: {exc}[/]", markup=True, highlight=False)
    finally:
        ui.flush()


def repl(agent: Agent, ui: RichUI, manager: ServerManager, cfg, online: bool, console: Console) -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory

    history = Path.home() / ".petru" / "history"
    history.parent.mkdir(parents=True, exist_ok=True)
    prompt_session: PromptSession = PromptSession("petru> ", history=FileHistory(str(history)))
    session = agent.session
    console.print(f"Petru ready. {_status(session, online)}. /help for commands.", markup=False)
    while True:
        try:
            line = prompt_session.prompt()
        except KeyboardInterrupt:
            console.print("(Ctrl+C: use /exit or Ctrl+D to quit)", markup=False)
            continue
        except EOFError:
            return
        if not line.strip():
            continue
        cmd = parse_command(line)
        if cmd is None:
            _run_turn(agent, ui, console, line)
        elif cmd.name == "exit":
            return
        elif cmd.name == "help":
            console.print(HELP_TEXT, markup=False)
        elif cmd.name == "status":
            console.print(_status(session, online), markup=False)
        elif cmd.name == "memory":
            section = memory_prompt_section(session.project_root, max_tokens=10_000)
            console.print(section or "No memories yet.", markup=False)
        elif cmd.name == "model":
            if cmd.arg:
                _switch_model(manager, agent, cfg, cmd.arg, console)
            else:
                console.print(f"Model tier: {session.tier}. Tiers: {', '.join(cfg.tiers)}", markup=False)
        elif cmd.name == "plan":
            if session.plan is None:
                console.print("No plan yet.", markup=False)
            else:
                steps = "\n".join(f"  {i}. {s}" for i, s in enumerate(session.plan.steps, start=1))
                state = "confirmed" if session.plan.confirmed else "proposed"
                console.print(f"Plan ({state}): {session.plan.title}\n{steps}", markup=False)
        elif cmd.name == "quick":
            if cmd.arg:
                _run_turn(agent, ui, console, cmd.arg, quick=True)
            else:
                console.print("Usage: /quick <request>", markup=False)
        elif cmd.name == "done":
            session.complete()
            console.print("Task closed; the next prompt starts a new design phase.", markup=False)
        elif cmd.name == "yolo":
            session.yolo = not session.yolo
            console.print(f"yolo {'on' if session.yolo else 'off'}", markup=False)
        else:
            console.print(f"Unknown command /{cmd.name}. /help lists the commands.", markup=False)


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    console = Console()
    err = Console(stderr=True)
    project = Path(ns.project).resolve()
    project.mkdir(parents=True, exist_ok=True)
    repo_root = find_repo_root(Path(__file__))
    cfg = load_config(repo_root)
    tier = ns.model or cfg.default_tier
    if tier not in cfg.tiers:
        err.print(f"Unknown tier {tier!r}. Tiers: {', '.join(cfg.tiers)}", markup=False)
        return 2
    ensure_repo(project)
    online = is_online()
    manager = ServerManager(cfg)
    try:
        base_url = manager.ensure_running(tier)
    except ServerStartError as exc:
        err.print(f"Cannot start the model server: {exc}", markup=False)
        return 2
    try:
        provider = make_provider(base_url)
        session = Session(project, tier=tier, yolo=ns.yolo)
        ui = NonInteractiveUI(err, yolo=ns.yolo) if ns.prompt is not None else RichUI(console)
        agent = Agent(
            provider=provider,
            registry=default_registry(online),
            ui=ui,
            session=session,
            repo_root=repo_root,
            ctx_tokens=cfg.tiers[tier].ctx,
            online=online,
        )
        if ns.prompt is not None:
            text = agent.run_turn(ns.prompt, quick=True)
            print(text)
            return 1 if agent.stop_reason in ("iteration limit", "invalid tool calls") else 0
        repl(agent, ui, manager, cfg, online, console)
        return 0
    finally:
        manager.stop()


if __name__ == "__main__":
    sys.exit(main())
