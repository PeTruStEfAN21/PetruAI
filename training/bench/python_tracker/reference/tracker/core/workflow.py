"""The status workflow: which moves are allowed and what each one requires."""

from ..config import Config
from ..errors import TransitionError
from ..models.enums import parse_status
from ..models.issue import Issue

TRANSITIONS = {
    "open": ("in_progress", "wontfix"),
    "in_progress": ("open", "review", "wontfix"),
    "review": ("in_progress", "done"),
    "done": ("open",),
    "wontfix": ("open",),
}


def next_statuses(status: str) -> list[str]:
    return list(TRANSITIONS[parse_status(status)])


def check_transition(
    issue: Issue,
    target: str,
    *,
    open_blockers: list[str],
    assignee_in_progress: int,
    config: Config,
) -> str:
    """Returns the normalized target status or raises TransitionError."""
    target = parse_status(target)
    if issue.status == target:
        raise TransitionError(f"{issue.key} is already {target}")
    if target not in TRANSITIONS[issue.status]:
        raise TransitionError(f"cannot move {issue.key} from {issue.status} to {target}")
    if target == "in_progress":
        if issue.assignee is None:
            raise TransitionError(f"cannot start {issue.key}: no assignee")
        if config.wip_limit is not None and assignee_in_progress >= config.wip_limit:
            raise TransitionError(f"wip limit reached for {issue.assignee}")
    if target == "done" and config.require_unblocked and open_blockers:
        raise TransitionError(f"{issue.key} is blocked by {', '.join(open_blockers)}")
    return target
