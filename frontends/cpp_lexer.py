"""Lexer for the Phase 1 C++ subset."""

from __future__ import annotations

import re

from .brace_lexer import lex_brace_language
from .tokens import Token


CPP_KEYWORDS = {
    "bool", "break", "case", "catch", "class", "const", "continue", "default", "do", "else", "false", "File", "float", "for", "if", "int", "new", "nullptr", "string", "switch", "try",
    "public", "return", "true", "void", "while",
}

_INCLUDE_LINE = re.compile(r'^\s*#\s*include\s*(?:<[^>\n]+>|"[^"\n]+")\s*(?://.*)?$', re.MULTILINE)
_PREPROCESSOR_LINE = re.compile(r'^\s*#', re.MULTILINE)


def _remove_include_directives(code: str) -> str:
    """Keep line positions while ignoring C++ headers in evaluator mode.

    Headers are meaningful to a native C++ compiler, but the teaching evaluator
    supplies its own tiny runtime. Replacing include-line characters with
    whitespace preserves the line numbering used by parser diagnostics.
    """
    def blank_line(match: re.Match[str]) -> str:
        return "".join("\n" if character == "\n" else " " for character in match.group())

    without_includes = _INCLUDE_LINE.sub(blank_line, code)
    remaining_directive = _PREPROCESSOR_LINE.search(without_includes)
    if remaining_directive is not None:
        line = without_includes.count("\n", 0, remaining_directive.start()) + 1
        raise SyntaxError(f"Unsupported C++ preprocessor directive at line {line}, column 1")
    return without_includes


def lex_cpp(code: str) -> list[Token]:
    """Return tokens for the C++ subset, accepting standard ``#include`` lines."""
    return lex_brace_language(_remove_include_directives(code), CPP_KEYWORDS)
