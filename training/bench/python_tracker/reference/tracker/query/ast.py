"""Nodes of a parsed search query."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Field:
    name: str
    op: str
    value: object


@dataclass(frozen=True)
class Not:
    child: object


@dataclass(frozen=True)
class And:
    children: tuple


@dataclass(frozen=True)
class Or:
    children: tuple


@dataclass(frozen=True)
class Query:
    """`filter` is None for an empty query; `sort` is a tuple of (field, descending)."""

    filter: object
    sort: tuple = ()
