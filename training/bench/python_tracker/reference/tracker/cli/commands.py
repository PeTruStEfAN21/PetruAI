"""One handler per subcommand; each returns the text to print."""

from pathlib import Path

from ..core.service import Tracker
from ..export import to_csv, to_markdown
from ..reports import by_assignee, by_label, by_status, render_table, report_rows
from .formatting import format_detail, format_entry, format_line


def user_cmd(tracker: Tracker, args) -> str:
    if args.action == "add":
        user = tracker.add_user(args.username, args.name, email=args.email, by=args.actor)
        return f"added user {user.username}"
    lines = []
    for user in tracker.users():
        line = f"{user.username}  {user.name}"
        lines.append(line + (f" <{user.email}>" if user.email else ""))
    return "\n".join(lines) or "no users"


def project_cmd(tracker: Tracker, args) -> str:
    if args.action == "add":
        project = tracker.add_project(args.key, args.name, by=args.actor)
        return f"added project {project.key}"
    return "\n".join(f"{p.key}  {p.name}" for p in tracker.projects()) or "no projects"


def new_cmd(tracker: Tracker, args) -> str:
    issue = tracker.create_issue(
        args.project,
        args.title,
        reporter=args.actor,
        description=args.description,
        priority=args.priority,
        labels=args.label,
        assignee=args.assignee,
    )
    return issue.key


def assign_cmd(tracker: Tracker, args) -> str:
    username = None if args.user == "none" else args.user
    issue = tracker.assign(args.key, username, by=args.actor)
    return f"{issue.key} assigned to {username}" if username else f"{issue.key} unassigned"


def move_cmd(tracker: Tracker, args) -> str:
    old = tracker.issue(args.key).status
    issue = tracker.transition(args.key, args.status, by=args.actor)
    return f"{issue.key}: {old} -> {issue.status}"


def label_cmd(tracker: Tracker, args) -> str:
    change = tracker.remove_label if args.remove else tracker.add_label
    issue = change(args.key, args.label, by=args.actor)
    return f"{issue.key} labels: {', '.join(issue.labels) or '-'}"


def comment_cmd(tracker: Tracker, args) -> str:
    comment = tracker.comment(args.key, args.body, by=args.actor)
    return f"added comment #{comment.id} to {args.key}"


def depend_cmd(tracker: Tracker, args) -> str:
    change = tracker.remove_dependency if args.remove else tracker.add_dependency
    issue = change(args.key, args.other, by=args.actor)
    return f"{issue.key} depends on: {', '.join(issue.depends_on) or '-'}"


def show_cmd(tracker: Tracker, args) -> str:
    return format_detail(tracker.issue(args.key))


def list_cmd(tracker: Tracker, args) -> str:
    issues = tracker.search(" ".join(args.query))
    return "\n".join(format_line(i) for i in issues) or "no issues"


def order_cmd(tracker: Tracker, args) -> str:
    issues = tracker.work_order(args.project)
    return "\n".join(f"{n}. {format_line(i)}" for n, i in enumerate(issues, 1)) or "no issues"


def report_cmd(tracker: Tracker, args) -> str:
    issues = tracker.issues(args.project)
    if args.kind == "status":
        return render_table(["status", "count"], [[s, n] for s, n in by_status(issues).items()])
    report = by_assignee(issues) if args.kind == "assignees" else by_label(issues)
    first = "assignee" if args.kind == "assignees" else "label"
    return render_table([first, "open", "closed", "total"], report_rows(report))


def export_cmd(tracker: Tracker, args) -> str:
    issues = tracker.search(" ".join(args.query))
    text = to_csv(issues) if args.format == "csv" else to_markdown(issues)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return f"wrote {len(issues)} issues to {args.output}"
    return text.rstrip("\n")


def log_cmd(tracker: Tracker, args) -> str:
    return "\n".join(format_entry(e) for e in tracker.audit(args.key)) or "no entries"


COMMANDS = {
    "user": user_cmd,
    "project": project_cmd,
    "new": new_cmd,
    "assign": assign_cmd,
    "move": move_cmd,
    "label": label_cmd,
    "comment": comment_cmd,
    "depend": depend_cmd,
    "show": show_cmd,
    "list": list_cmd,
    "order": order_cmd,
    "report": report_cmd,
    "export": export_cmd,
    "log": log_cmd,
}
