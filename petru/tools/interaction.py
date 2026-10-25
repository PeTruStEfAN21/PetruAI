"""Tools that talk to the user: design questions, the plan gate, and task completion."""

from __future__ import annotations

from petru.agent.decisions import append_decisions
from petru.agent.state import Phase, Plan
from petru.tools.base import Tool, ToolContext, ToolResult


def _no_ui() -> ToolResult:
    return ToolResult("No interactive user is available for this tool right now.", True)


class AskUserTool(Tool):
    name = "ask_user"
    description = (
        "Ask the user one short design question and wait for the answer. One question per call; "
        "offer options when the choice is between a few known alternatives."
    )
    parameters = {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional short list of choices",
            },
        },
        "required": ["question"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.ui is None:
            return _no_ui()
        question = str(args["question"])
        options = [str(o) for o in (args.get("options") or [])] or None
        answer = ctx.ui.ask(question, options)
        entry = f"{question} -> {answer}"
        if ctx.session is not None:
            if ctx.session.phase is Phase.BUILD:
                append_decisions(ctx.project_root, [entry])
            else:
                ctx.session.pending_decisions.append(entry)
        return ToolResult(answer)


class PlanTool(Tool):
    name = "plan"
    description = (
        "Propose the implementation plan after the design questions: a title, 3-8 concrete steps "
        "and the decisions taken. The user confirms, edits or rejects it; writing tools unlock "
        "only after confirmation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "decisions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "steps"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.ui is None or ctx.session is None:
            return _no_ui()
        session = ctx.session
        plan = Plan(
            title=str(args["title"]),
            steps=[str(s) for s in args["steps"]],
            decisions=[*session.pending_decisions, *[str(d) for d in (args.get("decisions") or [])]],
        )
        action = ctx.ui.show_plan(plan)
        edited = False
        if action == "edit":
            plan = ctx.ui.edit_plan(plan)
            edited = True
            action = "confirm"
        if action != "confirm":
            return ToolResult("Plan rejected by the user; ask what to change and propose a new plan.", True)
        session.plan = plan
        session.confirm_plan()
        session.pending_decisions = []
        append_decisions(
            ctx.project_root, [*plan.decisions, f"plan confirmat: {plan.title} ({len(plan.steps)} pași)"]
        )
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(plan.steps, start=1))
        prefix = "Plan confirmed (edited by the user)." if edited else "Plan confirmed."
        return ToolResult(f"{prefix} You are now in BUILD phase. Follow these steps:\n{steps}")


class TaskCompleteTool(Tool):
    name = "task_complete"
    description = (
        "Call when the task is finished and verified. Give a short summary of what was built "
        "and how it was checked."
    )
    parameters = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.session is not None:
            ctx.session.complete()
        return ToolResult(str(args["summary"]))


TOOLS: list[Tool] = [AskUserTool(), PlanTool(), TaskCompleteTool()]
