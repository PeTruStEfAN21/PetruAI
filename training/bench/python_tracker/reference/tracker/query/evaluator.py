"""Runs a parsed query against issues."""

import operator
from collections.abc import Iterable

from ..models.enums import STATUSES
from ..models.issue import Issue
from .ast import And, Field, Not, Or, Query, Text
from .parser import parse

COMPARE = {"=": operator.eq, ">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}

SORT_VALUES = {
    "priority": lambda issue: issue.priority,
    "created": lambda issue: issue.created,
    "updated": lambda issue: issue.updated,
    "key": Issue.sort_key,
    "status": lambda issue: STATUSES.index(issue.status),
    "title": lambda issue: issue.title.lower(),
}


def matches(node, issue: Issue) -> bool:
    if node is None:
        return True
    match node:
        case And(children):
            return all(matches(child, issue) for child in children)
        case Or(children):
            return any(matches(child, issue) for child in children)
        case Not(child):
            return not matches(child, issue)
        case Text(text):
            return text in issue.title.lower() or text in issue.description.lower()
        case Field():
            return _field_matches(node, issue)
    raise TypeError(f"not a query node: {node!r}")


def _field_matches(node: Field, issue: Issue) -> bool:
    name, value = node.name, node.value
    if name == "is":
        return issue.is_closed == (value == "closed")
    if name == "priority":
        return COMPARE[node.op](issue.priority, value)
    if name == "status":
        return issue.status in value
    if name == "label":
        return any(label in issue.labels for label in value)
    if name == "assignee":
        return any(issue.assignee is None if v == "none" else issue.assignee == v for v in value)
    if name == "reporter":
        return issue.reporter in value
    if name == "project":
        return issue.project in value
    raise ValueError(f"unknown field {name}")


def sort_issues(issues: Iterable[Issue], sort) -> list[Issue]:
    """Key order first, then each sort key from the last to the first (stable sorts)."""
    ordered = sorted(issues, key=Issue.sort_key)
    for name, descending in reversed(tuple(sort)):
        ordered.sort(key=SORT_VALUES[name], reverse=descending)
    return ordered


def search(issues: Iterable[Issue], query) -> list[Issue]:
    if isinstance(query, str):
        query = parse(query)
    assert isinstance(query, Query)
    return sort_issues((i for i in issues if matches(query.filter, i)), query.sort)
