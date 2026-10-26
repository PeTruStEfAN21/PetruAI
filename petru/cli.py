"""The `petru` command: start the local model server, then a REPL or a one-shot prompt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from petru.agent.loop import Agent
from petru.agent.state import Session
from petru.config import find_repo_root, load_config
from petru.journal.summarize import journal_prompt_section, summarize_pending
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
        elif cmd.name == "journal":
            section = journal_prompt_section(session.project_root, n=10, max_tokens=4_000)
            console.print(section or "No commit summaries yet (petru journal hook install).", markup=False)
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


SUBCOMMANDS = ("memory", "index", "watch", "journal")


def _journal_command(argv: list[str]) -> int:
    from petru.journal.hook import install_hook, uninstall_hook
    from petru.journal.summarize import summarize_pending

    parser = argparse.ArgumentParser(prog="petru journal", description="Commit journal: hook and summaries.")
    sub = parser.add_subparsers(dest="action", required=True)
    hook = sub.add_parser("hook", help="install or remove the git post-commit hook")
    hook.add_argument("mode", choices=["install", "uninstall"])
    hook.add_argument("--project", default=".")
    summ = sub.add_parser("summarize", help="summarize queued commits with the local model")
    summ.add_argument("--project", default=".")
    summ.add_argument("--model", choices=TIERS, default="fast")
    ns = parser.parse_args(argv)
    project = Path(ns.project).resolve()
    repo_root = find_repo_root(Path(__file__))
    if ns.action == "hook":
        if ns.mode == "install":
            print(f"Installed {install_hook(project, repo_root)}")
        else:
            uninstall_hook(project)
            print("Removed the PetruAI post-commit hook.")
        return 0
    manager = ServerManager(load_config(repo_root))
    try:
        provider = make_provider(manager.ensure_running(ns.model))
        print(f"Summarized {summarize_pending(project, provider)} commits.")
    except ServerStartError as exc:
        print(f"Cannot start the model server: {exc}", file=sys.stderr)
        return 2
    finally:
        manager.stop()
    return 0


def _watch_command(argv: list[str]) -> int:
    import time

    from petru.journal.store import Journal
    from petru.journal.watcher import ProjectWatcher

    parser = argparse.ArgumentParser(prog="petru watch", description="Journal every save in the project.")
    parser.add_argument("--project", default=".")
    parser.add_argument("--seconds", type=float, default=None, help="stop after this long (default: Ctrl+C)")
    ns = parser.parse_args(argv)
    project = Path(ns.project).resolve()
    journal = Journal(project / ".petru" / "journal.sqlite")
    known = journal.snapshot_all(project)
    watcher = ProjectWatcher(project, journal)
    watcher.start()
    print(f"Watching {project} ({known} files snapshotted). Ctrl+C to stop.", flush=True)
    seen = time.time()
    deadline = None if ns.seconds is None else time.monotonic() + ns.seconds
    try:
        while deadline is None or time.monotonic() < deadline:
            time.sleep(0.2)
            for event in journal.recent_events(since_ts=seen):
                print(f"{time.strftime('%H:%M:%S', time.localtime(event.ts))} {event.kind:8} {event.path}")
                seen = event.ts + 1e-6
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        journal.close()
    return 0


def _index_command(argv: list[str]) -> int:
    import time

    from petru.index import tools as index_tools
    from petru.index.embed_server import EmbedServer
    from petru.index.embeddings import Embedder
    from petru.index.store import CodeIndex

    parser = argparse.ArgumentParser(prog="petru index", description="Build or update the search indexes.")
    parser.add_argument("--project", default=".")
    parser.add_argument("--docs", action="store_true", help="index the Flutter SDK and offline docs instead")
    parser.add_argument("--no-embed", action="store_true", help="BM25 only, no embeddings server")
    ns = parser.parse_args(argv)
    repo_root = find_repo_root(Path(__file__))
    server = None if ns.no_embed else EmbedServer(load_config(repo_root))
    url = server.ensure() if server is not None else None
    if server is not None and url is None:
        print("Embeddings server unavailable: indexing for keyword search only.")
    embedder = Embedder(url) if url else None
    started = time.monotonic()
    try:
        if ns.docs:
            index = CodeIndex(index_tools.docs_index_path(), embedder)
            for label, root in index_tools.docs_roots(repo_root).items():
                stats = index.update(root, prefix=label)
                print(
                    f"{label}: {stats['added']} added, {stats['updated']} updated, {stats['removed']} removed"
                )
        else:
            project = Path(ns.project).resolve()
            index = CodeIndex(project / ".petru" / "index.sqlite", embedder)
            index.update(project)
        totals = index.stats()
        index.close()
    finally:
        if server is not None:
            server.stop()
    print(f"{totals['files']} files, {totals['chunks']} chunks, {totals['embedded']} embedded "
          f"in {time.monotonic() - started:.0f} s")  # fmt: skip
    return 0


def _memory_command(argv: list[str]) -> int:
    from petru.memory.transfer import export_memory, import_memory

    parser = argparse.ArgumentParser(prog="petru memory", description="Export or import what Petru learned.")
    sub = parser.add_subparsers(dest="action", required=True)
    exp = sub.add_parser("export", help="write global and project memory to a zip")
    exp.add_argument("zip", type=Path)
    only = exp.add_mutually_exclusive_group()
    only.add_argument("--global-only", action="store_true")
    only.add_argument("--project-only", action="store_true")
    exp.add_argument("--project", default=".")
    imp = sub.add_parser("import", help="merge a zip into this machine's memory (never overwrites)")
    imp.add_argument("zip", type=Path)
    imp.add_argument("--project", default=".")
    ns = parser.parse_args(argv)
    project = Path(ns.project).resolve()
    if ns.action == "export":
        count = export_memory(
            ns.zip, project, include_global=not ns.project_only, include_project=not ns.global_only
        )
        print(f"Exported {count} files to {ns.zip}")
        return 0
    counts = import_memory(ns.zip, project)
    print(f"Imported: {counts['added']} added, {counts['merged']} merged, {counts['skipped']} skipped")
    return 0


def run_subcommand(argv: list[str]) -> int | None:
    """`petru memory ...` and friends; None means "not a subcommand", so the REPL/one-shot parser runs."""
    if not argv or argv[0] not in SUBCOMMANDS:
        return None
    if argv[0] == "index":
        return _index_command(argv[1:])
    if argv[0] == "watch":
        return _watch_command(argv[1:])
    if argv[0] == "journal":
        return _journal_command(argv[1:])
    return _memory_command(argv[1:])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    handled = run_subcommand(argv)
    if handled is not None:
        return handled
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
        try:  # lazy journal: summarize a few queued commits while the model is loaded anyway
            done = summarize_pending(project, provider, limit=3)
            if done:
                console.print(f"Journal: summarized {done} new commits (/journal).", markup=False)
        except Exception as exc:  # the journal is a convenience; never block the REPL on it
            console.print(f"Journal summaries skipped: {exc}", markup=False)
        repl(agent, ui, manager, cfg, online, console)
        return 0
    finally:
        manager.stop()


if __name__ == "__main__":
    sys.exit(main())
