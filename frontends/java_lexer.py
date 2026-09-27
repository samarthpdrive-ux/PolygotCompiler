"""Lexer for the Phase 1 Java subset."""

from __future__ import annotations

import re

from .brace_lexer import lex_brace_language
from .tokens import Token


JAVA_KEYWORDS = {
    "boolean", "break", "case", "catch", "class", "continue", "default", "do", "double", "else", "extends", "false", "File", "for", "if", "int", "new", "null", "String", "super", "switch", "try",
    "private", "public", "return", "static", "this", "true", "void", "while",
}

_JAVA_DIRECTIVE_LINE = re.compile(r"^\s*(?:package|import)\s+[^;]+;\s*$", re.MULTILINE)
_JAVA_MODIFIER = re.compile(r"\b(?:public|private|protected)\b")


def _normalize_java_wrapper(code: str) -> str:
    """Remove Java file-wrapper syntax that has no runtime role in this evaluator."""
    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if character == "\n" else " " for character in match.group())

    normalized = _JAVA_DIRECTIVE_LINE.sub(blank, code)
    return _JAVA_MODIFIER.sub(blank, normalized)


def lex_java(code: str) -> list[Token]:
    """Return tokens for the Java subset, accepting standard file wrappers."""
    return lex_brace_language(_normalize_java_wrapper(code), JAVA_KEYWORDS)
