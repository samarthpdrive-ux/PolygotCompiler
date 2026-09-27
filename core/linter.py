"""Lightweight semantic lint rules for the shared AST."""

from __future__ import annotations

from .ast_nodes import Block, FunctionDeclaration, Program, ReturnStatement, Statement, VariableDeclaration


def lint_program(program: Program) -> list[str]:
    """Report duplicate declarations and unreachable statements."""
    messages: list[str] = []

    def visit_block(block: Block, context: str) -> None:
        declared: set[str] = set()
        terminated = False
        for statement in block.statements:
            if terminated:
                messages.append(f"unreachable statement {type(statement).__name__} in {context}")
            if isinstance(statement, VariableDeclaration):
                if statement.name in declared:
                    messages.append(f"duplicate declaration of {statement.name!r} in {context}")
                declared.add(statement.name)
            if isinstance(statement, ReturnStatement):
                terminated = True
            if isinstance(statement, Block):
                visit_block(statement, context)
            elif isinstance(statement, FunctionDeclaration):
                visit_block(statement.body, statement.name)
            else:
                for value in getattr(statement, "__dict__", {}).values():
                    if isinstance(value, Block):
                        visit_block(value, context)
        
    for statement in program.statements:
        if isinstance(statement, FunctionDeclaration):
            visit_block(statement.body, statement.name)
        elif isinstance(statement, Block):
            visit_block(statement, "program")
    return messages
