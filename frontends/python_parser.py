"""Phase 2 parser entry point for Python token streams."""

from __future__ import annotations

from collections.abc import Iterable

from core.ast_nodes import Program
from core.parser import Parser
from .tokens import Token


def parse_python(tokens: Iterable[Token]) -> Program:
    """Parse indentation-based Python assignments, conditionals, and loops."""
    return Parser(tokens, style="indent").parse()


def parse_python_recovering(tokens: Iterable[Token]) -> tuple[Program, tuple[object, ...]]:
    """Return the partial Python AST and every recoverable parser diagnostic."""
    return Parser(tokens, style="indent").parse_recovering()
