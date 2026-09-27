"""Lexer for the Phase 1 indentation-based Python subset."""

from __future__ import annotations

import re
from ast import literal_eval

from .tokens import Token


PYTHON_KEYWORDS = {
    "and", "break", "case", "class", "continue", "def", "elif", "else", "except", "False", "for", "if", "in", "match", "None",
    "not", "or", "return", "self", "True", "try", "while", "import", "with", "as",
}

LINE_PATTERN = re.compile(
    "|".join(
        (
            r"(?P<COMMENT>\#.*)",
            r'(?P<STRING>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')',
            r"(?P<NUMBER>\b\d+(?:\.\d+)?\b)",
            r"(?P<IDENTIFIER>\b[A-Za-z_]\w*\b)",
            r"(?P<OP>\+=|-=|\*=|/=|%=|==|!=|<=|>=|//|\*\*|[+\-*/%<>])",
            r"(?P<ASSIGN>=)",
            r"(?P<DOT>\.)",
            r"(?P<SYMBOL>[:(),\[\]{}])",
            r"(?P<SKIP>[ \t]+)",
            r"(?P<MISMATCH>.)",
        )
    )
)


class PythonLexer:
    """Tokenize simple Python syntax while recording INDENT and DEDENT tokens."""

    def lex(self, code: str) -> list[Token]:
        tokens: list[Token] = []
        indent_stack = [0]
        lines = code.splitlines()

        for line_number, raw_line in enumerate(lines, start=1):
            if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip(" \t"))]:
                raise SyntaxError(f"Tabs are not supported for indentation at line {line_number}")

            content = raw_line.lstrip(" ")
            if not content or content.startswith("#"):
                continue

            indentation = len(raw_line) - len(content)
            if indentation > indent_stack[-1]:
                indent_stack.append(indentation)
                tokens.append(Token("INDENT", indentation, line_number, 1))
            while indentation < indent_stack[-1]:
                indent_stack.pop()
                tokens.append(Token("DEDENT", indentation, line_number, 1))
            if indentation != indent_stack[-1]:
                raise SyntaxError(f"Inconsistent indentation at line {line_number}")

            self._lex_line(content, line_number, indentation + 1, tokens)
            tokens.append(Token("NEWLINE", "\\n", line_number, len(raw_line) + 1))

        final_line = len(lines) + 1
        while len(indent_stack) > 1:
            indent_stack.pop()
            tokens.append(Token("DEDENT", indent_stack[-1], final_line, 1))
        return tokens

    @staticmethod
    def _lex_line(content: str, line: int, first_column: int, tokens: list[Token]) -> None:
        position = 0
        while position < len(content):
            match = LINE_PATTERN.match(content, position)
            if match is None:
                raise RuntimeError("Lexer pattern failed to advance")

            token_type = match.lastgroup
            value = match.group()
            column = first_column + position
            position = match.end()

            if token_type == "COMMENT":
                return
            if token_type == "NUMBER":
                number = float(value) if "." in value else int(value)
                tokens.append(Token("NUMBER", number, line, column))
            elif token_type == "STRING":
                tokens.append(Token("STRING", literal_eval(value), line, column))
            elif token_type == "IDENTIFIER":
                kind = "KEYWORD" if value in PYTHON_KEYWORDS else "IDENTIFIER"
                tokens.append(Token(kind, value, line, column))
            elif token_type in {"ASSIGN", "OP", "DOT", "SYMBOL"}:
                tokens.append(Token(token_type, value, line, column))
            elif token_type == "MISMATCH":
                raise SyntaxError(f"Unexpected character {value!r} at line {line}, column {column}")


def lex_python(code: str) -> list[Token]:
    """Return tokens for Python expressions and indentation-based blocks."""
    return PythonLexer().lex(code)
