"""Phase 2 parser entry point for C++ token streams."""

from __future__ import annotations

from collections.abc import Iterable

from core.ast_nodes import Program
from core.parser import Parser
from .tokens import Token


def parse_cpp(tokens: Iterable[Token]) -> Program:
    """Parse C++ assignments, arithmetic, conditionals, and while blocks."""
    return Parser(
        tokens,
        style="brace",
        declaration_keywords={"int", "float", "bool", "string", "File", "const"},
        function_return_keywords={"int", "float", "bool", "string", "void"},
    ).parse()


def parse_cpp_recovering(tokens: Iterable[Token]) -> tuple[Program, tuple[object, ...]]:
    """Return the partial C++ AST and every recoverable parser diagnostic."""
    return Parser(
        tokens, style="brace",
        declaration_keywords={"int", "float", "bool", "string", "File", "const"},
        function_return_keywords={"int", "float", "bool", "string", "void"},
    ).parse_recovering()
