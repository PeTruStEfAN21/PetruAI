"""One session's commands, shared by the line REPL and the full-screen view. Each reports what it did through
`say`, so both views show the same messages."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING

from petru.agent import team
from petru.agent.loop import Agent
from petru.agent.state import Phase
from petru.journal.summarize import journal_prompt_section
from petru.memory.tools import memory_prompt_section
from petru.server import ServerStartError
from petru.tui.commands import HELP_TEXT, parse_command

if TYPE_CHECKING:
    from petru.cli import TeamModes


class App:
    def __init__(
        self, agent: Agent, manager, cfg, modes: TeamModes, online: bool, say: Callable[[str], None]
    ) -> None:
        self.agent, self.manager, self.cfg, self.modes, self.online = agent, manager, cfg, modes, online
        self.say = say
        self.busy = False  # a turn or a model switch is running

    @property
    def session(self):
        return self.agent.session

    @property
    def thinking(self) -> bool:
        return bool(getattr(self.agent.provider, "thinking", False))

    @property
    def team_on(self) -> bool:
        return self.agent.registry is self.modes.team

    def in_task(self) -> bool:
        """The model and the team cannot change now: a turn runs, or a task is between its turns."""
        return self.busy or self.session.phase is not Phase.IDLE

    def context_share(self) -> int:
        """How full the context was at the last request, in percent."""
        agent = self.agent
        return round(100 * agent.usage.prompt_tokens / agent.ctx_tokens) if agent.ctx_tokens else 0

    def speed(self) -> float | None:
        usage = self.agent.usage
        return usage.completion_tokens / usage.model_seconds if usage.model_seconds else None

    # -- what the commands show ---------------------------------------------

    def status(self) -> str:
        session = self.session
        return (
            f"phase={session.phase.value} tier={session.tier} project={session.project_root} "
            f"{'online' if self.online else 'offline'}{' yolo' if session.yolo else ''}"
            f"{' think' if self.thinking else ''}"
        )

    def details(self) -> str:
        agent, session, usage = self.agent, self.session, self.agent.usage
        tier = self.cfg.tiers.get(session.tier)
        speed = self.speed()
        lines = [
            f"model    {session.tier} ({tier.model_file if tier else '?'})",
            f"context  {usage.prompt_tokens:,} of {agent.ctx_tokens:,} tokens ({self.context_share()}%)",
            f"replies  {usage.requests} request{'' if usage.requests == 1 else 's'}, "
            f"{usage.completion_tokens:,} tokens in "
            f"{usage.model_seconds:.0f} s{f', {speed:.1f} tok/s' if speed else ''}",
            f"tools    {usage.tool_calls} calls",
            f"stopped  {(agent.stop_reason or 'answered') if usage.requests else 'none yet'}",
            f"think    {'on' if self.thinking else 'off'}",
        ]
        if self.team_on:
            choice, delegate = agent.registry.get("choose_mode"), agent.registry.get("delegate")
            mode = getattr(choice, "mode", None) or "not chosen yet"
            reason = getattr(choice, "reason", None)
            authors = Counter(team.credits(agent.registry).values())
            files = ", ".join(f"{who} {n}" for who, n in sorted(authors.items()))
            lines.append(
                f"team     on: {mode}{f' ({reason})' if reason else ''}, "
                f"{getattr(delegate, 'calls', 0)} delegations{f'; files: {files}' if files else ''}"
            )
        else:
            lines.append("team     off (/team switches it on)")
        plan = session.plan
        planned = f", plan: {plan.title} ({'confirmed' if plan.confirmed else 'proposed'})" if plan else ""
        lines.append(f"phase    {session.phase.value}{planned}")
        return "\n".join(lines)

    # -- switches -------------------------------------------------------------

    def switch_model(self, tier: str) -> None:
        cfg = self.cfg
        if tier == "auto":  # the promoted language specialist for this project, else the general fine-tune
            from petru.router import choose_tier

            fallback = "tuned" if "tuned" in cfg.tiers else cfg.default_tier
            tier = choose_tier(self.session.project_root, cfg.tiers, fallback)
        if tier not in cfg.tiers:
            self.say(f"Unknown tier {tier!r}. Tiers: {', '.join(cfg.tiers)}")
            return
        try:
            self.manager.ensure_running(tier)
        except ServerStartError as exc:
            self.say(str(exc))
            return
        self.session.tier = tier
        self.agent.ctx_tokens = cfg.tiers[tier].ctx
        self.agent.max_iterations = cfg.tiers[tier].max_iterations
        self.say(f"Model tier: {tier} ({cfg.tiers[tier].model_file})")

    def toggle_team(self) -> None:
        session = self.session
        if session.phase is not Phase.IDLE:  # the lead's tools and role must not change in mid-task
            self.say("Finish the current task first (/done), then switch.")
            return
        if self.team_on:
            self.agent.registry, session.role = self.modes.solo, ""
            self.say(f"Team mode off: {session.tier} works alone.")
            return
        self.agent.registry, session.role = self.modes.lead(), team.LEAD_PROMPT
        if session.tier != "quality" and "quality" in self.cfg.tiers:  # the 35B leads, as with --team
            self.switch_model("quality")
        self.say(f"Team mode on: {session.tier} leads; the assistant starts on its first delegation.")

    def toggle_think(self) -> None:
        self.agent.provider.thinking = not self.thinking
        self.say(f"think {'on' if self.thinking else 'off'}")

    def toggle_yolo(self) -> None:
        self.session.yolo = not self.session.yolo
        self.say(f"yolo {'on' if self.session.yolo else 'off'}")

    # -- turns and commands ---------------------------------------------------

    def run_turn(self, text: str, quick: bool = False) -> None:
        if self.session.phase is Phase.IDLE:  # a new task: in team mode the lead chooses again
            team.start_task(self.agent.registry)
        self.busy = True
        try:
            self.agent.run_turn(text, quick=quick)
        except KeyboardInterrupt:
            self.say("Turn cancelled.")
        except Exception as exc:  # the session survives a provider/tool crash; the error is shown
            self.say(f"{type(exc).__name__}: {exc}")
        finally:
            flush = getattr(self.agent.ui, "flush", None)
            if flush is not None:
                flush()
            self.busy = False

    def handle(self, line: str) -> bool:
        """Run one line typed at the prompt: a slash command or a request. True means quit."""
        cmd = parse_command(line)
        session = self.session
        if cmd is None:
            self.run_turn(line)
        elif cmd.name == "exit":
            return True
        elif cmd.name == "help":
            self.say(HELP_TEXT)
        elif cmd.name == "status":
            self.say(self.status())
        elif cmd.name == "details":
            self.say(self.details())
        elif cmd.name == "team":
            self.toggle_team()
        elif cmd.name == "think":
            self.toggle_think()
        elif cmd.name == "memory":
            section = memory_prompt_section(session.project_root, max_tokens=10_000)
            self.say(section or "No memories yet.")
        elif cmd.name == "journal":
            section = journal_prompt_section(session.project_root, n=10, max_tokens=4_000)
            self.say(section or "No commit summaries yet (petru journal hook install).")
        elif cmd.name == "model":
            if cmd.arg:
                self.switch_model(cmd.arg)
            else:
                self.say(f"Model tier: {session.tier}. Tiers: {', '.join(self.cfg.tiers)}, auto")
        elif cmd.name == "plan":
            if session.plan is None:
                self.say("No plan yet.")
            else:
                steps = "\n".join(f"  {i}. {s}" for i, s in enumerate(session.plan.steps, start=1))
                state = "confirmed" if session.plan.confirmed else "proposed"
                self.say(f"Plan ({state}): {session.plan.title}\n{steps}")
        elif cmd.name == "quick":
            if cmd.arg:
                self.run_turn(cmd.arg, quick=True)
            else:
                self.say("Usage: /quick <request>")
        elif cmd.name == "done":
            session.complete()
            self.say("Task closed; the next prompt starts a new design phase.")
        elif cmd.name == "yolo":
            self.toggle_yolo()
        else:
            self.say(f"Unknown command /{cmd.name}. /help lists the commands.")
        return False
