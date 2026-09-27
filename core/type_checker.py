"""Small static type checker for the documented polyglot subset.

The checker deliberately reports only definite incompatibilities.  Unknown
function/object results stay ``unknown`` so that it does not reject programs
which the dynamic evaluator can execute safely.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import (
    ArrayDeclaration, Assignment, BinaryOperation, Block, BooleanLiteral,
    ClassDeclaration, Expression, ForEachStatement, ForStatement,
    FunctionDeclaration, Identifier, IfStatement, IndexAccess, ListLiteral,
    MappingLiteral, NewExpression, Node, NullLiteral, NumberLiteral,
    ObjectDeclaration, Program, SetLiteral, Statement, StringLiteral, TupleLiteral,
    SwitchStatement, TryStatement, UnaryOperation, VariableDeclaration,
    WhileStatement, ReturnStatement,
)


@dataclass(frozen=True, slots=True)
class TypeDiagnostic:
    """A non-fatal source-level type issue."""

    message: str


class TypeChecker:
    """Infer simple values and find incompatible typed declarations/assignments."""

    _NORMALIZED = {
        "int": "int", "float": "float", "double": "float",
        "bool": "bool", "boolean": "bool", "string": "string", "String": "string",
    }

    def __init__(self) -> None:
        self.diagnostics: list[TypeDiagnostic] = []
        self._scopes: list[dict[str, str]] = [{}]
        self._return_type: str | None = None

    def check(self, program: Program) -> list[TypeDiagnostic]:
        self._visit(program)
        return self.diagnostics

    def _visit(self, node: Node | None) -> None:
        if node is None:
            return
        if isinstance(node, Program | Block):
            for statement in node.statements:
                self._visit(statement)
        elif isinstance(node, VariableDeclaration):
            actual = self._infer(node.value) if node.value is not None else "null"
            expected = self._normalise(node.declared_type)
            self._declare(node.name, expected)
            self._report_if_incompatible(node.name, expected, actual)
        elif isinstance(node, ArrayDeclaration):
            expected = f"list[{self._normalise(node.declared_type)}]"
            self._declare(node.name, expected)
            if node.values is not None:
                for value in node.values:
                    self._report_if_incompatible(node.name, self._normalise(node.declared_type), self._infer(value))
        elif isinstance(node, Assignment):
            if isinstance(node.target, Identifier):
                expected = self._lookup(node.target.name)
                if expected is not None:
                    self._report_if_incompatible(node.target.name, expected, self._infer(node.value))
            self._visit_expression_children(node.value)
        elif isinstance(node, (IfStatement, WhileStatement)):
            self._visit_expression_children(node.condition)
            self._visit(node.then_branch if isinstance(node, IfStatement) else node.body)
            if isinstance(node, IfStatement):
                self._visit(node.else_branch)
        elif isinstance(node, ForStatement):
            self._push_scope()
            self._visit(node.initializer)
            self._visit_expression_children(node.condition)
            self._visit(node.update)
            self._visit(node.body)
            self._pop_scope()
        elif isinstance(node, ForEachStatement):
            self._push_scope()
            self._declare(node.name, self._normalise(node.declared_type or "unknown"))
            self._visit_expression_children(node.iterable)
            self._visit(node.body)
            self._pop_scope()
        elif isinstance(node, FunctionDeclaration):
            previous_return = self._return_type
            self._return_type = self._normalise(node.return_type) if node.return_type else None
            self._push_scope()
            for index, parameter in enumerate(node.parameters):
                parameter_type = node.parameter_types[index] if index < len(node.parameter_types) else "unknown"
                self._declare(parameter, self._normalise(parameter_type))
            self._visit(node.body)
            self._pop_scope()
            self._return_type = previous_return
        elif isinstance(node, ReturnStatement):
            if self._return_type is not None:
                self._report_if_incompatible("return value", self._return_type, self._infer(node.value))
        elif isinstance(node, ClassDeclaration):
            for attribute in node.attributes:
                self._visit(attribute)
            for method in [*node.methods, *node.constructors]:
                self._visit(method)
        elif isinstance(node, ObjectDeclaration):
            self._declare(node.name, node.class_name)
        elif isinstance(node, SwitchStatement):
            self._visit_expression_children(node.expression)
            for case in node.cases:
                self._visit_expression_children(case.value)
                self._visit(case.body)
        elif isinstance(node, TryStatement):
            self._visit(node.try_branch)
            self._visit(node.except_branch)

    def _infer(self, expression: Expression | None) -> str:
        if expression is None or isinstance(expression, NullLiteral):
            return "null"
        if isinstance(expression, NumberLiteral):
            return "float" if isinstance(expression.value, float) else "int"
        if isinstance(expression, BooleanLiteral):
            return "bool"
        if isinstance(expression, StringLiteral):
            return "string"
        if isinstance(expression, ListLiteral):
            return "list"
        if isinstance(expression, MappingLiteral):
            return "map"
        if isinstance(expression, SetLiteral):
            return "set"
        if isinstance(expression, TupleLiteral):
            return "tuple"
        if isinstance(expression, Identifier):
            return self._lookup(expression.name) or "unknown"
        if isinstance(expression, IndexAccess):
            return "unknown"
        if isinstance(expression, NewExpression):
            return expression.class_name
        if isinstance(expression, UnaryOperation):
            return "bool" if expression.operator in {"!", "not"} else self._infer(expression.operand)
        if isinstance(expression, BinaryOperation):
            if expression.operator in {"==", "!=", "<", "<=", ">", ">=", "and", "or", "&&", "||", "in"}:
                return "bool"
            left, right = self._infer(expression.left), self._infer(expression.right)
            if expression.operator == "+" and "string" in {left, right}:
                return "string"
            return "float" if "float" in {left, right} else left if left == right else "unknown"
        return "unknown"

    def _visit_expression_children(self, expression: Expression | None) -> None:
        # Inference is sufficient today; this hook keeps future expression checks central.
        self._infer(expression)

    def _report_if_incompatible(self, name: str, expected: str, actual: str) -> None:
        if actual in {"unknown", "null"} or expected in {"unknown", "list", "map", "set"}:
            return
        if expected == "float" and actual == "int":
            return
        if expected != actual:
            self.diagnostics.append(TypeDiagnostic(
                f"Type mismatch for {name!r}: expected {expected}, got {actual}."
            ))

    def _normalise(self, value: str) -> str:
        if value.startswith("const "):
            value = value[6:]
        return self._NORMALIZED.get(value, value)

    def _declare(self, name: str, value_type: str) -> None:
        self._scopes[-1][name] = value_type

    def _lookup(self, name: str) -> str | None:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return None

    def _push_scope(self) -> None:
        self._scopes.append({})

    def _pop_scope(self) -> None:
        self._scopes.pop()


def check_types(program: Program) -> list[TypeDiagnostic]:
    """Return definite type issues without executing source code."""
    return TypeChecker().check(program)
