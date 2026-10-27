"""Dependencies between issues: cycle detection and a topological work order."""

import heapq
from collections.abc import Iterable, Mapping

from ..errors import CycleError
from ..models.issue import Issue, key_order


class DependencyGraph:
    """Edges point from an issue to the issues it depends on."""

    def __init__(self, edges: Mapping[str, Iterable[str]]):
        self._edges = {key: sorted(deps, key=key_order) for key, deps in edges.items()}

    def dependencies(self, key: str) -> list[str]:
        return list(self._edges.get(key, ()))

    def dependents(self, key: str) -> list[str]:
        return sorted((k for k, deps in self._edges.items() if key in deps), key=key_order)

    def find_path(self, start: str, goal: str) -> list[str] | None:
        """A path start -> ... -> goal following dependencies, or None."""
        seen = set()

        def visit(node):
            if node == goal:
                return [node]
            seen.add(node)
            for nxt in self._edges.get(node, ()):
                if nxt not in seen:
                    rest = visit(nxt)
                    if rest is not None:
                        return [node, *rest]
            return None

        return visit(start)

    def check_new_edge(self, key: str, depends_on: str) -> None:
        if key == depends_on:
            raise CycleError([key, key])
        path = self.find_path(depends_on, key)
        if path is not None:
            raise CycleError([key, *path])


def work_order(issues: Iterable[Issue]) -> list[Issue]:
    """Open issues with every open dependency first; ties go to higher priority, then lower key."""
    pending = {issue.key: issue for issue in issues if not issue.is_closed}
    waiting = {key: {d for d in issue.depends_on if d in pending} for key, issue in pending.items()}
    dependents: dict[str, list[str]] = {key: [] for key in pending}
    for key, deps in waiting.items():
        for dep in deps:
            dependents[dep].append(key)

    def entry(key):
        issue = pending[key]
        return (-issue.priority, *issue.sort_key(), key)

    ready = [entry(key) for key, deps in waiting.items() if not deps]
    heapq.heapify(ready)
    order = []
    while ready:
        key = heapq.heappop(ready)[-1]
        order.append(pending[key])
        for child in dependents[key]:
            waiting[child].discard(key)
            if not waiting[child]:
                heapq.heappush(ready, entry(child))
    if len(order) != len(pending):
        stuck = sorted((k for k in pending if waiting[k]), key=key_order)
        raise CycleError(stuck)
    return order
