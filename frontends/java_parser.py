"""Phase 2 parser entry point for Java token streams."""

from __future__ import annotations

from collections.abc import Iterable

from core.ast_nodes import Program
from core.parser import Parser
from .tokens import Token


def parse_java(tokens: Iterable[Token]) -> Program:
    """Parse Java assignments, arithmetic, conditionals, and while blocks."""
    return Parser(
        tokens,
        style="brace",
        declaration_keywords={"int", "double", "boolean", "String", "File"},
        function_return_keywords={"int", "double", "boolean", "String", "void"},
    ).parse()


def parse_java_recovering(tokens: Iterable[Token]) -> tuple[Program, tuple[object, ...]]:
    """Return the partial Java AST and every recoverable parser diagnostic."""
    return Parser(
        tokens, style="brace",
        declaration_keywords={"int", "double", "boolean", "String", "File"},
        function_return_keywords={"int", "double", "boolean", "String", "void"},
    ).parse_recovering()
