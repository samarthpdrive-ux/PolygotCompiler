"""Compatibility wrapper for the original C-style Phase 1 lexer name."""

from .cpp_lexer import lex_cpp
from .tokens import Token


def lex(code: str) -> list[Token]:
    """Tokenize the supported C-style subset using the C++ lexer."""
    return lex_cpp(code)
