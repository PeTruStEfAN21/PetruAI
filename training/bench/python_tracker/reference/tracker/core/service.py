"""The Tracker facade: every change is validated, written to the audit log and saved."""

import time
from collections.abc import Callable, Iterable
from pathlib import Path

from ..config import Config
from ..errors import DuplicateError, NotFoundError
from ..models.entities import AuditEntry, Project, User
from ..models.enums import parse_priority
from ..models.issue import Comment, Issue, key_order, parse_key
from ..query import search as run_search
from ..storage import load_state, save_state
from ..validators import (
    require_text,
    validate_email,
    validate_label,
    validate_project_key,
    validate_title,
    validate_username,
)
from .dependencies import DependencyGraph, work_order
from .workflow import check_transition


class Tracker:
    def __init__(self, path, *, clock: Callable[[], int] | None = None, config: Config | None = None):
        self.path = Path(path)
        self.clock = clock or (lambda: int(time.time()))
        self.config = config or Config()
        self._state = load_state(self.path)

    # users and projects

    def add_user(self, username: str, name: str, *, email: str | None = None, by: str = "system") -> User:
        validate_username(username)
        if username in self._state.users:
            raise DuplicateError(f"user '{username}' already exists")
        if email is not None:
            validate_email(email)
        user = User(username, require_text(name, "name"), email)
        self._state.users[username] = user
        self._log(by, "user", None, username, self.clock())
        return user

    def user(self, username: str) -> User:
        try:
            return self._state.users[username]
        except KeyError:
            raise NotFoundError(f"unknown user '{username}'") from None

    def users(self) -> list[User]:
        return [self._state.users[name] for name in sorted(self._state.users)]

    def add_project(self, key: str, name: str, *, by: str = "system") -> Project:
        validate_project_key(key)
        if key in self._state.projects:
            raise DuplicateError(f"project '{key}' already exists")
        project = Project(key, require_text(name, "name"))
        self._state.projects[key] = project
        self._state.counters.setdefault(key, 0)
        self._log(by, "project", None, key, self.clock())
        return project

    def project(self, key: str) -> Project:
        try:
            return self._state.projects[key]
        except KeyError:
            raise NotFoundError(f"unknown project '{key}'") from None

    def projects(self) -> list[Project]:
        return [self._state.projects[key] for key in sorted(self._state.projects)]

    # issues

    def create_issue(
        self,
        project: str,
        title: str,
        *,
        reporter: str,
        description: str = "",
        priority=None,
        labels: Iterable[str] = (),
        assignee: str | None = None,
    ) -> Issue:
        self.project(project)
        self.user(reporter)
        title = validate_title(title)
        priority = self.config.default_priority if priority is None else parse_priority(priority)
        labels = sorted({validate_label(label) for label in labels})
        if assignee is not None:
            self.user(assignee)
        number = self._state.counters.get(project, 0) + 1
        now = self.clock()
        issue = Issue(
            project=project,
            number=number,
            title=title,
            reporter=reporter,
            description=description.strip(),
            priority=priority,
            assignee=assignee,
            labels=labels,
            created=now,
            updated=now,
        )
        self._state.counters[project] = number
        self._state.issues[issue.key] = issue
        self._log(reporter, "create", issue.key, title, now)
        return issue

    def issue(self, key: str) -> Issue:
        issue = self._state.issues.get(key)
        if issue is None:
            parse_key(key)
            raise NotFoundError(f"unknown issue '{key}'")
        return issue

    def issues(self, project: str | None = None) -> list[Issue]:
        if project is not None:
            self.project(project)
        found = (i for i in self._state.issues.values() if project is None or i.project == project)
        return sorted(found, key=Issue.sort_key)

    def edit(self, key: str, *, title: str | None = None, description: str | None = None, by: str = "system") -> Issue:
        issue = self.issue(key)
        changed = []
        if title is not None and validate_title(title) != issue.title:
            issue.title = validate_title(title)
            changed.append("title")
        if description is not None and description.strip() != issue.description:
            issue.description = description.strip()
            changed.append("description")
        if changed:
            self._change(issue, by, "edit", ",".join(changed))
        return issue

    def assign(self, key: str, username: str | None, *, by: str = "system") -> Issue:
        issue = self.issue(key)
        if username is not None:
            self.user(username)
        if issue.assignee != username:
            issue.assignee = username
            self._change(issue, by, "assign", username or "none")
        return issue

    def transition(self, key: str, status: str, *, by: str = "system") -> Issue:
        issue = self.issue(key)
        busy = sum(
            1
            for other in self._state.issues.values()
            if other is not issue and other.status == "in_progress" and other.assignee == issue.assignee
        )
        target = check_transition(
            issue,
            status,
            open_blockers=self.blockers(key),
            assignee_in_progress=busy,
            config=self.config,
        )
        old, issue.status = issue.status, target
        self._change(issue, by, "status", f"{old} -> {target}")
        return issue

    def set_priority(self, key: str, priority, *, by: str = "system") -> Issue:
        issue = self.issue(key)
        new = parse_priority(priority)
        if new != issue.priority:
            old, issue.priority = issue.priority, new
            self._change(issue, by, "priority", f"{old} -> {new}")
        return issue

    def add_label(self, key: str, label: str, *, by: str = "system") -> Issue:
        issue = self.issue(key)
        validate_label(label)
        if label not in issue.labels:
            issue.labels = sorted([*issue.labels, label])
            self._change(issue, by, "label", f"+{label}")
        return issue

    def remove_label(self, key: str, label: str, *, by: str = "system") -> Issue:
        issue = self.issue(key)
        if label not in issue.labels:
            raise NotFoundError(f"{key} has no label '{label}'")
        issue.labels.remove(label)
        self._change(issue, by, "label", f"-{label}")
        return issue

    def comment(self, key: str, body: str, *, by: str) -> Comment:
        issue = self.issue(key)
        self.user(by)
        body = require_text(body, "comment")
        now = self.clock()
        comment = Comment(len(issue.comments) + 1, by, body, now)
        issue.comments.append(comment)
        self._change(issue, by, "comment", str(comment.id), now)
        return comment

    # dependencies

    def add_dependency(self, key: str, depends_on: str, *, by: str = "system") -> Issue:
        issue = self.issue(key)
        self.issue(depends_on)
        if depends_on in issue.depends_on:
            raise DuplicateError(f"{key} already depends on {depends_on}")
        self._graph().check_new_edge(key, depends_on)
        issue.depends_on = sorted([*issue.depends_on, depends_on], key=key_order)
        self._change(issue, by, "depend", f"+{depends_on}")
        return issue

    def remove_dependency(self, key: str, depends_on: str, *, by: str = "system") -> Issue:
        issue = self.issue(key)
        if depends_on not in issue.depends_on:
            raise NotFoundError(f"{key} does not depend on {depends_on}")
        issue.depends_on.remove(depends_on)
        self._change(issue, by, "depend", f"-{depends_on}")
        return issue

    def blockers(self, key: str) -> list[str]:
        """The dependencies of `key` that are still open."""
        issue = self.issue(key)
        return [d for d in issue.depends_on if not self._state.issues[d].is_closed]

    def dependents(self, key: str) -> list[str]:
        self.issue(key)
        return self._graph().dependents(key)

    def work_order(self, project: str) -> list[Issue]:
        return work_order(self.issues(project))

    # queries and history

    def search(self, query: str) -> list[Issue]:
        return run_search(self._state.issues.values(), query)

    def audit(self, key: str | None = None) -> list[AuditEntry]:
        if key is not None:
            self.issue(key)
        return [e for e in self._state.audit if key is None or e.key == key]

    # internals

    def _graph(self) -> DependencyGraph:
        return DependencyGraph({k: i.depends_on for k, i in self._state.issues.items()})

    def _change(self, issue: Issue, actor: str, action: str, detail: str, now: int | None = None) -> None:
        now = self.clock() if now is None else now
        issue.updated = now
        self._log(actor, action, issue.key, detail, now)

    def _log(self, actor: str, action: str, key: str | None, detail: str, now: int) -> None:
        self._state.audit.append(AuditEntry(len(self._state.audit) + 1, now, actor, action, key, detail))
        save_state(self.path, self._state)
