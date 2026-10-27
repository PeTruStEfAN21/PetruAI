"""Recursive descent parser for the search language.

    query   := or_expr
    or_expr := and_expr ("OR" and_expr)*
    and_expr:= unary+
    unary   := "-" unary | primary
    primary := "(" or_expr ")" | field_term | text
"""

from ..errors import QuerySyntaxError, ValidationError
from ..models.enums import STATUSES, parse_priority
from .ast import And, Field, Not, Or, Query, Text
from .tokenizer import Token, tokenize

FIELDS = ("status", "is", "label", "assignee", "reporter", "project", "priority")
SORT_FIELDS = ("priority", "created", "updated", "key", "status", "title")


def parse(text: str) -> Query:
    tokens, sort = _extract_sort(tokenize(text))
    return Query(_Parser(tokens).parse(), tuple(sort))


def _extract_sort(tokens: list[Token]):
    """Pulls the sort: terms out; they are only allowed outside parentheses and negations."""
    rest, sort, depth = [], [], 0
    for index, tok in enumerate(tokens):
        if tok.kind == "LPAREN":
            depth += 1
        elif tok.kind == "RPAREN":
            depth -= 1
        if tok.kind == "TERM" and tok.value[0] == "sort":
            negated = index > 0 and tokens[index - 1].kind == "NOT"
            if depth > 0 or negated:
                raise QuerySyntaxError("sort is only allowed at the top level", tok.pos)
            sort.extend(_sort_keys(tok))
            continue
        rest.append(tok)
    return rest, sort


def _sort_keys(tok: Token):
    _, op, raw = tok.value
    if op != ":":
        raise QuerySyntaxError(f"operator '{op}' is not allowed for 'sort'", tok.pos)
    if not raw:
        raise QuerySyntaxError("missing value for 'sort'", tok.pos)
    keys = []
    for part in raw.lower().split(","):
        descending = part.startswith("-")
        name = part[1:] if descending else part
        if name not in SORT_FIELDS:
            raise QuerySyntaxError(f"unknown sort field '{name}'", tok.pos)
        keys.append((name, descending))
    return keys


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    def peek(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> Token | None:
        tok = self.peek()
        self.index += 1
        return tok

    def parse(self):
        if not self.tokens:
            return None
        node = self.or_expr()
        leftover = self.peek()
        if leftover is not None:  # only an unmatched ")" stops the top level early
            raise QuerySyntaxError("unbalanced parentheses", leftover.pos)
        return node

    def or_expr(self):
        branches = [self.and_expr()]
        while (tok := self.peek()) is not None and tok.kind == "OR":
            self.take()
            branches.append(self.and_expr())
        return branches[0] if len(branches) == 1 else Or(tuple(branches))

    def and_expr(self):
        items = [self.unary()]
        while (tok := self.peek()) is not None and tok.kind not in ("OR", "RPAREN"):
            items.append(self.unary())
        return items[0] if len(items) == 1 else And(tuple(items))

    def unary(self):
        tok = self.peek()
        if tok is not None and tok.kind == "NOT":
            self.take()
            return Not(self.unary())
        return self.primary()

    def primary(self):
        tok = self.take()
        if tok is None:
            raise QuerySyntaxError("expected a term")
        if tok.kind == "LPAREN":
            node = self.or_expr()
            close = self.take()
            if close is None or close.kind != "RPAREN":
                raise QuerySyntaxError("unbalanced parentheses", tok.pos)
            return node
        if tok.kind == "TEXT":
            return Text(tok.value.lower())
        if tok.kind == "TERM":
            return _field(tok)
        raise QuerySyntaxError("expected a term", tok.pos)


def _field(tok: Token) -> Field:
    name, op, raw = tok.value
    if name not in FIELDS:
        raise QuerySyntaxError(f"unknown field '{name}'", tok.pos)
    if op != ":" and name != "priority":
        raise QuerySyntaxError(f"operator '{op}' is not allowed for '{name}'", tok.pos)
    if not raw:
        raise QuerySyntaxError(f"missing value for '{name}'", tok.pos)
    if name == "priority":
        try:
            value = parse_priority(raw)
        except ValidationError:
            raise QuerySyntaxError(f"invalid priority '{raw}'", tok.pos) from None
        return Field(name, "=" if op == ":" else op, value)
    if name == "is":
        value = raw.lower()
        if value not in ("open", "closed"):
            raise QuerySyntaxError(f"invalid value '{raw}' for 'is'", tok.pos)
        return Field(name, ":", value)
    values = tuple(v for v in raw.split(",") if v)
    if name == "project":
        values = tuple(v.upper() for v in values)
    else:
        values = tuple(v.lower() for v in values)
    if name == "status":
        for value in values:
            if value not in STATUSES:
                raise QuerySyntaxError(f"unknown status '{value}'", tok.pos)
    return Field(name, ":", values)
