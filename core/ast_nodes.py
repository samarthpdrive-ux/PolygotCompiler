"""Abstract Syntax Tree nodes for Phase 2 parsing.

Nodes describe program structure only. They carry no execution behaviour;
the evaluator introduced in a later phase will visit these nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Node:
    """Base class for all AST nodes."""


class Statement(Node):
    """Base class for executable statements."""


class Expression(Node):
    """Base class for expressions that produce a value."""


@dataclass(frozen=True, slots=True)
class Program(Node):
    statements: list[Statement]


@dataclass(frozen=True, slots=True)
class Block(Statement):
    statements: list[Statement]


@dataclass(frozen=True, slots=True)
class Assignment(Statement):
    target: Expression
    value: Expression


@dataclass(frozen=True, slots=True)
class VariableDeclaration(Statement):
    declared_type: str
    name: str
    value: Expression | None = None


@dataclass(frozen=True, slots=True)
class ArrayDeclaration(Statement):
    """A typed brace-language array declaration."""

    declared_type: str
    name: str
    size: Expression | None = None
    values: list[Expression] | None = None


@dataclass(frozen=True, slots=True)
class IfStatement(Statement):
    condition: Expression
    then_branch: Block
    else_branch: Block | None = None


@dataclass(frozen=True, slots=True)
class WhileStatement(Statement):
    condition: Expression
    body: Block


@dataclass(frozen=True, slots=True)
class ForStatement(Statement):
    """A counted loop represented by an initializer, condition, and update."""

    initializer: Statement
    condition: Expression
    update: Statement
    body: Block


@dataclass(frozen=True, slots=True)
class ForEachStatement(Statement):
    """Iterate over each list or string value in a language-specific collection loop."""

    name: str
    iterable: Expression
    body: Block
    declared_type: str | None = None


@dataclass(frozen=True, slots=True)
class DoWhileStatement(Statement):
    """A brace-language loop whose body is guaranteed to execute once."""

    body: Block
    condition: Expression


@dataclass(frozen=True, slots=True)
class BreakStatement(Statement):
    """Exit the innermost active loop."""


@dataclass(frozen=True, slots=True)
class ContinueStatement(Statement):
    """Skip directly to the next iteration of the innermost active loop."""


@dataclass(frozen=True, slots=True)
class SwitchCase(Node):
    """One value-labelled (or default) branch in a switch/match statement."""

    value: Expression | None
    body: Block


@dataclass(frozen=True, slots=True)
class SwitchStatement(Statement):
    """A multi-way branch with optional C++/Java fall-through semantics."""

    expression: Expression
    cases: list[SwitchCase]
    fall_through: bool = True


@dataclass(frozen=True, slots=True)
class TryStatement(Statement):
    """A protected block followed by one evaluator exception handler block."""

    try_branch: Block
    except_branch: Block


@dataclass(frozen=True, slots=True)
class FunctionDeclaration(Statement):
    name: str
    parameters: list[str]
    body: Block
    return_type: str | None = None
    is_static: bool = False
    parameter_types: list[str] = field(default_factory=list)
    parameter_by_reference: list[bool] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReturnStatement(Statement):
    value: Expression | None = None


@dataclass(frozen=True, slots=True)
class ClassDeclaration(Statement):
    name: str
    attributes: list[VariableDeclaration]
    methods: list[FunctionDeclaration]
    constructors: list[FunctionDeclaration] = field(default_factory=list)
    parent_name: str | None = None
    static_attributes: list[VariableDeclaration] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ObjectDeclaration(Statement):
    class_name: str
    name: str
    constructor_arguments: list[Expression]


@dataclass(frozen=True, slots=True)
class ExpressionStatement(Statement):
    expression: Expression


@dataclass(frozen=True, slots=True)
class InputStatement(Statement):
    """Read one value into a C++ ``cin >> variable`` target."""

    target: Expression


@dataclass(frozen=True, slots=True)
class OutputStatement(Statement):
    """A lightweight C++ ``cout``/``cerr`` stream output statement."""

    stream: str
    values: list[Expression]


@dataclass(frozen=True, slots=True)
class SuperConstructorCall(Statement):
    """An explicit Java ``super(arguments);`` constructor call."""

    arguments: list[Expression]


@dataclass(frozen=True, slots=True)
class ImportStatement(Statement):
    """A safe allow-listed Python module import."""

    module: str


@dataclass(frozen=True, slots=True)
class WithFileStatement(Statement):
    """A Python ``with open(...) as file:`` block for sandboxed files."""

    resource: Expression
    name: str
    body: Block


@dataclass(frozen=True, slots=True)
class NumberLiteral(Expression):
    value: int | float


@dataclass(frozen=True, slots=True)
class BooleanLiteral(Expression):
    value: bool


@dataclass(frozen=True, slots=True)
class NullLiteral(Expression):
    """The shared evaluator representation for null/nullptr/None."""


@dataclass(frozen=True, slots=True)
class StringLiteral(Expression):
    value: str


@dataclass(frozen=True, slots=True)
class ListLiteral(Expression):
    elements: list[Expression]


@dataclass(frozen=True, slots=True)
class MappingLiteral(Expression):
    """A Python dictionary literal, represented as expression pairs."""

    entries: list[tuple[Expression, Expression]]


@dataclass(frozen=True, slots=True)
class SetLiteral(Expression):
    """A Python set literal, represented as element expressions."""

    elements: list[Expression]


@dataclass(frozen=True, slots=True)
class TupleLiteral(Expression):
    """An immutable Python-style ordered literal."""

    elements: list[Expression]


@dataclass(frozen=True, slots=True)
class ListComprehension(Expression):
    """One Python list-comprehension clause: ``[value for value in items]``."""

    element: Expression
    name: str
    iterable: Expression


@dataclass(frozen=True, slots=True)
class Identifier(Expression):
    name: str


@dataclass(frozen=True, slots=True)
class MemberAccess(Expression):
    object: Expression
    member: str


@dataclass(frozen=True, slots=True)
class IndexAccess(Expression):
    object: Expression
    index: Expression


@dataclass(frozen=True, slots=True)
class CallExpression(Expression):
    callee: Expression
    arguments: list[Expression]


@dataclass(frozen=True, slots=True)
class NewExpression(Expression):
    class_name: str
    arguments: list[Expression]


@dataclass(frozen=True, slots=True)
class UnaryOperation(Expression):
    operator: str
    operand: Expression


@dataclass(frozen=True, slots=True)
class BinaryOperation(Expression):
    left: Expression
    operator: str
    right: Expression
