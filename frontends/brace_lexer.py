"""Shared regular-expression scanner for C++- and Java-style source code."""

from __future__ import annotations

import re
from ast import literal_eval
from collections.abc import Iterable

from .tokens import Token


TOKEN_PATTERN = re.compile(
    "|".join(
        (
            r"(?P<COMMENT>//[^\n]*|/\*[\s\S]*?\*/)",
            r'(?P<STRING>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')',
            r"(?P<NUMBER>\b\d+(?:\.\d+)?\b)",
            r"(?P<IDENTIFIER>\b[A-Za-z_]\w*\b)",
            r"(?P<OP>\+\+|--|\+=|-=|\*=|/=|%=|>>|<<|==|!=|<=|>=|&&|\|\||[+\-*/%<>&!])",
            r"(?P<ASSIGN>=)",
            r"(?P<DOT>\.)",
            r"(?P<SYMBOL>[{}();,:\[\]])",
            r"(?P<NEWLINE>\r?\n)",
            r"(?P<SKIP>[ \t\r]+)",
            r"(?P<MISMATCH>.)",
        )
    )
)


def lex_brace_language(code: str, keywords: Iterable[str]) -> list[Token]:
    """Tokenize a curly-brace language using the supplied keyword set."""
    keyword_set = set(keywords)
    tokens: list[Token] = []
    line = 1
    line_start = 0

    for match in TOKEN_PATTERN.finditer(code):
        token_type = match.lastgroup
        value = match.group()
        column = match.start() - line_start + 1

        if token_type == "NUMBER":
            number = float(value) if "." in value else int(value)
            tokens.append(Token("NUMBER", number, line, column))
        elif token_type == "STRING":
            tokens.append(Token("STRING", literal_eval(value), line, column))
        elif token_type == "IDENTIFIER":
            kind = "KEYWORD" if value in keyword_set else "IDENTIFIER"
            tokens.append(Token(kind, value, line, column))
        elif token_type in {"ASSIGN", "OP", "DOT", "SYMBOL"}:
            tokens.append(Token(token_type, value, line, column))
        elif token_type == "MISMATCH":
            raise SyntaxError(f"Unexpected character {value!r} at line {line}, column {column}")

        if token_type in {"NEWLINE", "COMMENT"} and "\n" in value:
            line += value.count("\n")
            line_start = match.start() + value.rfind("\n") + 1

    return tokens
