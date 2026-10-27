"""Splits a search query into tokens."""

import re
from dataclasses import dataclass

from ..errors import QuerySyntaxError

FIELD_TERM = re.compile(r"([A-Za-z_]+)(>=|<=|:|=|>|<)(.*)", re.DOTALL)
WORD_STOP = '()"'


@dataclass(frozen=True)
class Token:
    kind: str  # LPAREN, RPAREN, NOT, OR, TERM (value = (field, op, raw)) or TEXT
    value: object
    pos: int


def tokenize(text: str) -> list[Token]:
    tokens = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "(":
            tokens.append(Token("LPAREN", ch, i))
            i += 1
        elif ch == ")":
            tokens.append(Token("RPAREN", ch, i))
            i += 1
        elif ch == "-" and i + 1 < n and not text[i + 1].isspace():
            tokens.append(Token("NOT", ch, i))
            i += 1
        elif ch == '"':
            end = text.find('"', i + 1)
            if end == -1:
                raise QuerySyntaxError("unterminated quote", i)
            tokens.append(Token("TEXT", text[i + 1 : end], i))
            i = end + 1
        else:
            start = i
            while i < n and not text[i].isspace() and text[i] not in WORD_STOP:
                i += 1
            tokens.append(_word(text[start:i], start))
    return tokens


def _word(word: str, pos: int) -> Token:
    if word == "OR":
        return Token("OR", word, pos)
    match = FIELD_TERM.fullmatch(word)
    if match:
        return Token("TERM", (match[1].lower(), match[2], match[3]), pos)
    return Token("TEXT", word, pos)
