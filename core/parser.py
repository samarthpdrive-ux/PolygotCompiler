"""Shared recursive-descent parser for the Phase 2 language subsets."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from .ast_nodes import (
    Assignment,
    ArrayDeclaration,
    BinaryOperation,
    Block,
    BooleanLiteral,
    BreakStatement,
    CallExpression,
    ClassDeclaration,
    ContinueStatement,
    DoWhileStatement,
    Expression,
    ExpressionStatement,
    ForStatement,
    ForEachStatement,
    FunctionDeclaration,
    Identifier,
    InputStatement,
    ImportStatement,
    IfStatement,
    IndexAccess,
    ListComprehension,
    ListLiteral,
    MappingLiteral,
    MemberAccess,
    NewExpression,
    NumberLiteral,
    NullLiteral,
    ObjectDeclaration,
    OutputStatement,
    Program,
    ReturnStatement,
    StringLiteral,
    SetLiteral,
    SuperConstructorCall,
    TupleLiteral,
    SwitchCase,
    SwitchStatement,
    TryStatement,
    WithFileStatement,
    Statement,
    UnaryOperation,
    VariableDeclaration,
    WhileStatement,
)
if TYPE_CHECKING:
    # Keeping this import type-only prevents a dependency cycle when a
    # frontend imports Parser while its package is still initializing.
    from frontends.tokens import Token


@dataclass(frozen=True, slots=True)
class ParseDiagnostic:
    """One recoverable parser error with a source position."""

    message: str
    line: int
    column: int

    def format(self) -> str:
        return f"SYNTAX [PARSE] line {self.line}, column {self.column}: {self.message}"


class Parser:
    """Parse Phase 1 tokens into an AST for one block-syntax style."""

    _PRECEDENCE = {
        "or": 1, "||": 1,
        "and": 2, "&&": 2,
        "==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3, "in": 3,
        "+": 4, "-": 4,
        "*": 5, "/": 5, "%": 5,
    }
    _BOOLEAN_VALUES = {"True": True, "False": False, "true": True, "false": False}

    def __init__(
        self,
        tokens: Iterable[Token],
        *,
        style: str,
        declaration_keywords: Iterable[str] = (),
        function_return_keywords: Iterable[str] = (),
    ) -> None:
        if style not in {"brace", "indent"}:
            raise ValueError("style must be 'brace' or 'indent'")
        self.tokens = list(tokens)
        self.style = style
        self.declaration_keywords = set(declaration_keywords)
        self.function_return_keywords = set(function_return_keywords)
        self.position = 0

    def parse(self) -> Program:
        """Parse every token into a top-level program node."""
        statements = self._parse_statements_until(end_symbol=None)
        if self.current is not None:
            self._error("Unexpected token after program")
        return Program(statements)

    def parse_recovering(self) -> tuple[Program, tuple[ParseDiagnostic, ...]]:
        """Parse independent statements while collecting recoverable errors.

        This is intentionally a reporting API: normal ``parse()`` remains
        strict for execution. Synchronization stops at a simple-statement
        boundary (semicolon/newline/closing brace) so one malformed statement
        does not hide later diagnostics.
        """
        statements: list[Statement] = []
        diagnostics: list[ParseDiagnostic] = []
        self._skip_newlines()
        while self.current is not None:
            # A failed nested brace block may leave its closing delimiter at
            # top level after synchronization. It belongs to the abandoned
            # construct, not to a new diagnostic.
            if self.style == "brace" and self._matches("SYMBOL", "}"):
                self._advance()
                self._skip_newlines()
                continue
            if self.style == "indent" and self._matches("DEDENT"):
                self._advance()
                self._skip_newlines()
                continue
            try:
                statements.append(self._parse_statement())
            except SyntaxError as error:
                diagnostics.append(self._diagnostic_from_error(error))
                self._synchronize()
            self._skip_newlines()
        return Program(statements), tuple(diagnostics)

    def _diagnostic_from_error(self, error: SyntaxError) -> ParseDiagnostic:
        message = str(error)
        match = re.search(r" at line (\d+), column (\d+)$", message)
        if match is not None:
            line, column = (int(value) for value in match.groups())
            return ParseDiagnostic(message[:match.start()], line, column)
        if self.current is not None:
            return ParseDiagnostic(message, self.current.line, self.current.column)
        if self.tokens:
            token = self.tokens[-1]
            return ParseDiagnostic(message, token.line, token.column)
        return ParseDiagnostic(message, 1, 1)

    def _synchronize(self) -> None:
        """Discard the malformed portion of one statement without looping."""
        if self.current is None:
            return
        if self.style == "indent":
            while self.current is not None and self.current.type not in {"NEWLINE", "DEDENT"}:
                self._advance()
            self._skip_newlines()
            return
        while self.current is not None:
            token = self._advance()
            if token.type == "SYMBOL" and token.value in {";", "}"}:
                return

    @property
    def current(self) -> Token | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _advance(self) -> Token:
        token = self.current
        if token is None:
            raise SyntaxError("Unexpected end of input")
        self.position += 1
        return token

    def _matches(self, token_type: str, value: object | None = None) -> bool:
        token = self.current
        return token is not None and token.type == token_type and (value is None or token.value == value)

    def _match(self, token_type: str, value: object | None = None) -> Token | None:
        if self._matches(token_type, value):
            return self._advance()
        return None

    def _expect(self, token_type: str, value: object | None = None, message: str | None = None) -> Token:
        token = self._match(token_type, value)
        if token is None:
            if message is not None:
                expected = message
            elif value is not None:
                expected = f"Expected {value!r}"
            else:
                expected = f"Expected {token_type}"
            self._error(expected)
        return token

    def _error(self, message: str) -> None:
        token = self.current
        if token is None:
            raise SyntaxError(f"{message} at end of input")
        raise SyntaxError(f"{message} at line {token.line}, column {token.column}")

    def _skip_newlines(self) -> None:
        while self._match("NEWLINE") is not None:
            pass

    def _parse_statements_until(self, end_symbol: str | None) -> list[Statement]:
        statements: list[Statement] = []
        self._skip_newlines()
        while self.current is not None:
            if end_symbol is not None and self._matches("SYMBOL", end_symbol):
                break
            if self.style == "indent" and self._matches("DEDENT"):
                break
            statements.append(self._parse_statement())
            self._skip_newlines()
        return statements

    def _parse_statement(self) -> Statement:
        """Parse and annotate one statement with its source line."""
        line = self.current.line if self.current is not None else None
        statement = self._parse_statement_unmarked()
        if line is not None:
            # Node deliberately keeps a normal instance dictionary even though
            # concrete AST nodes use slots, allowing tooling metadata without
            # changing the public dataclass constructors.
            object.__setattr__(statement, "source_line", line)
        return statement

    def _parse_statement_unmarked(self) -> Statement:
        if self.style == "brace" and self._matches("KEYWORD", "class"):
            return self._parse_class()
        if self.style == "indent" and self._matches("KEYWORD", "def"):
            return self._parse_function()
        if self.style == "indent" and self._matches("KEYWORD", "import"):
            return self._parse_import()
        if self.style == "indent" and self._matches("KEYWORD", "with"):
            return self._parse_with_file()
        if self._matches("KEYWORD", "if"):
            return self._parse_if()
        if self._matches("KEYWORD", "while"):
            return self._parse_while()
        if self._matches("KEYWORD", "for"):
            return self._parse_for()
        if self.style == "brace" and self._matches("KEYWORD", "do"):
            return self._parse_do_while()
        if self.style == "brace" and self._matches("KEYWORD", "switch"):
            return self._parse_switch()
        if self.style == "indent" and self._matches("KEYWORD", "match"):
            return self._parse_match()
        if self._matches("KEYWORD", "try"):
            return self._parse_try()
        if self._matches("KEYWORD", "break"):
            self._advance()
            self._finish_simple_statement()
            return BreakStatement()
        if self._matches("KEYWORD", "continue"):
            self._advance()
            self._finish_simple_statement()
            return ContinueStatement()
        if self._matches("KEYWORD", "return"):
            return self._parse_return()
        if self.style == "brace" and self._matches("KEYWORD", "super"):
            return self._parse_super_constructor_call()
        if self.style == "brace" and self._matches("IDENTIFIER", "cin") and self._looks_like_cpp_input():
            return self._parse_cpp_input()
        if self.style == "brace" and self._matches("IDENTIFIER") and str(self.current.value) in {"cout", "cerr"} and self._looks_like_cpp_output():
            return self._parse_cpp_output()
        if self.style == "brace" and self._looks_like_typed_function():
            return self._parse_function()
        if self.style == "brace" and self._looks_like_object_declaration():
            return self._parse_object_declaration()
        return self._parse_assignment_or_declaration()

    def _looks_like_cpp_input(self) -> bool:
        return self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].type == "OP" and self.tokens[self.position + 1].value == ">>"

    def _parse_cpp_input(self) -> InputStatement:
        """Parse a compact C++ input statement: ``cin >> variable;``."""
        self._advance()  # cin
        self._expect("OP", ">>", "Expected '>>' after 'cin'")
        target: Expression = Identifier(str(self._expect("IDENTIFIER", message="Expected variable after 'cin >>'").value))
        while self._match("DOT") is not None:
            member = self._expect("IDENTIFIER", message="Expected member name after '.'")
            target = MemberAccess(target, str(member.value))
        self._finish_simple_statement()
        return InputStatement(target)

    def _looks_like_cpp_output(self) -> bool:
        return self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].type == "OP" and self.tokens[self.position + 1].value == "<<"

    def _parse_cpp_output(self) -> OutputStatement:
        """Parse ``cout << value << endl;`` without modelling C++ streams."""
        stream = str(self._advance().value)
        values: list[Expression] = []
        while self._match("OP", "<<") is not None:
            values.append(self._parse_expression())
        self._finish_simple_statement()
        return OutputStatement(stream, values)

    def _looks_like_typed_function(self) -> bool:
        """Identify ``int name(...)`` without confusing it with a declaration."""
        if self.current is None or self.current.value not in self.function_return_keywords:
            return False
        if self.position + 2 >= len(self.tokens):
            return False
        name, opening_parenthesis = self.tokens[self.position + 1 : self.position + 3]
        return name.type == "IDENTIFIER" and opening_parenthesis.type == "SYMBOL" and opening_parenthesis.value == "("

    def _looks_like_object_declaration(self) -> bool:
        """Identify ``ClassName object;`` and ``ClassName object = new ...``."""
        if self.current is None or self.current.type != "IDENTIFIER":
            return False
        if self.position + 1 >= len(self.tokens):
            return False
        return self.tokens[self.position + 1].type == "IDENTIFIER" or (
            self.tokens[self.position + 1].type == "OP" and self.tokens[self.position + 1].value == "<"
        )

    def _parse_assignment_or_declaration(self, *, finish_statement: bool = True) -> Statement:
        declared_type: str | None = None
        array_type_marker = False
        if self.current is not None and self.current.value in self.declaration_keywords:
            declared_type = str(self._advance().value)
            if declared_type == "const":
                base = self._expect("KEYWORD", message="Expected type after 'const'")
                declared_type = f"const {base.value}"
            if self._match("SYMBOL", "[") is not None:
                self._expect("SYMBOL", "]", "Expected ']' after array type")
                array_type_marker = True

        if declared_type is not None:
            name = self._expect("IDENTIFIER", message="Expected variable name").value
        elif self._matches("IDENTIFIER") or self._matches("KEYWORD", "this") or self._matches("KEYWORD", "self"):
            name = self._advance().value
        else:
            self._error("Expected variable name")

        array_size: Expression | None = None
        if declared_type is not None and self._match("SYMBOL", "[") is not None:
            if not self._matches("SYMBOL", "]"):
                array_size = self._parse_expression()
            self._expect("SYMBOL", "]", "Expected ']' after array size")
            array_type_marker = True

        if declared_type is not None and array_type_marker:
            values: list[Expression] | None = None
            if self._match("ASSIGN", "=") is not None:
                values = self._parse_array_initializer()
            elif array_size is None:
                self._error("Array declaration needs a size or initializer")
            if finish_statement:
                self._finish_simple_statement()
            return ArrayDeclaration(declared_type, str(name), array_size, values)

        if declared_type is not None and self.style == "brace" and self._matches("SYMBOL", ";"):
            self._advance()
            return VariableDeclaration(declared_type, str(name))

        target = self._parse_postfix(Identifier(str(name)))
        if self._match("ASSIGN", "=") is None:
            if self._matches("OP") and self.current.value in {"+=", "-=", "*=", "/=", "%="}:
                operator = str(self._advance().value)[0]
                value = self._parse_expression()
                if finish_statement:
                    self._finish_simple_statement()
                return Assignment(target, BinaryOperation(target, operator, value))
            if self.style == "brace" and self._matches("OP") and self.current.value in {"++", "--"}:
                operator = "+" if self._advance().value == "++" else "-"
                if finish_statement:
                    self._finish_simple_statement()
                return Assignment(target, BinaryOperation(target, operator, NumberLiteral(1)))
            if declared_type is not None:
                self._error("Expected '=' after variable name")
            expression = self._parse_postfix(target)
            expression = self._parse_binary_expression(expression)
            if finish_statement:
                self._finish_simple_statement()
            return ExpressionStatement(expression)

        value = self._parse_expression()
        if finish_statement:
            self._finish_simple_statement()

        if declared_type is not None:
            return VariableDeclaration(declared_type, str(name), value)
        return Assignment(target, value)

    def _parse_object_declaration(self) -> ObjectDeclaration:
        class_name = str(self._expect("IDENTIFIER").value)
        if self._match("OP", "<") is not None:
            self._skip_generic_arguments()
        name = str(self._expect("IDENTIFIER", message="Expected object variable name").value)
        arguments: list[Expression] = []
        if self._match("ASSIGN", "=") is not None:
            self._expect("KEYWORD", "new", "Expected 'new' for object construction")
            constructor_type = str(self._expect("IDENTIFIER", message="Expected class name after 'new'").value)
            if constructor_type != class_name:
                self._error(f"Cannot assign new {constructor_type} to {class_name}")
            arguments = self._parse_call_arguments()
        self._finish_simple_statement()
        return ObjectDeclaration(class_name, name, arguments)

    def _skip_generic_arguments(self) -> None:
        """Skip one simple ``<T>`` or ``<K, V>`` collection type annotation."""
        depth = 1
        while depth:
            token = self._advance()
            if token.type == "OP" and token.value == "<":
                depth += 1
            elif token.type == "OP" and token.value == ">":
                depth -= 1

    def _parse_super_constructor_call(self) -> SuperConstructorCall:
        self._advance()  # super
        arguments = self._parse_call_arguments()
        self._finish_simple_statement()
        return SuperConstructorCall(arguments)

    def _finish_simple_statement(self) -> None:
        if self.style == "brace":
            self._expect("SYMBOL", ";", "Expected ';' after statement")
        else:
            self._expect("NEWLINE", message="Expected end of Python statement")

    def _parse_if(self) -> IfStatement:
        self._advance()  # 'if'
        condition = self._parse_expression()
        then_branch = self._parse_suite()
        else_branch = None
        if self._match("KEYWORD", "elif") is not None:
            else_branch = self._parse_elif_chain()
        elif self._match("KEYWORD", "else") is not None:
            if self._match("KEYWORD", "if") is not None:
                else_branch = self._parse_elif_chain()
            else:
                else_branch = self._parse_suite()
        return IfStatement(condition, then_branch, else_branch)

    def _parse_elif_chain(self) -> Block:
        """Parse the condition after ``elif`` or ``else if`` into a nested AST."""
        condition = self._parse_expression()
        then_branch = self._parse_suite()
        else_branch: Block | None = None
        if self._match("KEYWORD", "elif") is not None:
            else_branch = self._parse_elif_chain()
        elif self._match("KEYWORD", "else") is not None:
            if self._match("KEYWORD", "if") is not None:
                else_branch = self._parse_elif_chain()
            else:
                else_branch = self._parse_suite()
        return Block([IfStatement(condition, then_branch, else_branch)])

    def _parse_while(self) -> WhileStatement:
        self._advance()  # 'while'
        condition = self._parse_expression()
        return WhileStatement(condition, self._parse_suite())

    def _parse_for(self) -> ForStatement:
        """Parse brace-language counted loops and Python ``range`` loops."""
        self._advance()  # 'for'
        if self.style == "brace":
            self._expect("SYMBOL", "(", "Expected '(' after 'for'")
            if self._looks_like_brace_foreach():
                declared_type = None
                if self.current is not None and self.current.value in self.declaration_keywords:
                    declared_type = str(self._advance().value)
                name = str(self._expect("IDENTIFIER", message="Expected loop variable name").value)
                self._expect("SYMBOL", ":", "Expected ':' after loop variable")
                iterable = self._parse_expression()
                self._expect("SYMBOL", ")", "Expected ')' after collection")
                return ForEachStatement(name, iterable, self._parse_suite(), declared_type)
            initializer = self._parse_assignment_or_declaration()
            condition = self._parse_expression()
            self._expect("SYMBOL", ";", "Expected ';' after for-loop condition")
            update = self._parse_assignment_or_declaration(finish_statement=False)
            self._expect("SYMBOL", ")", "Expected ')' after for-loop update")
            return ForStatement(initializer, condition, update, self._parse_suite())

        name = str(self._expect("IDENTIFIER", message="Expected loop variable after 'for'").value)
        self._expect("KEYWORD", "in", "Expected 'in' after Python loop variable")
        if self._matches("IDENTIFIER", "range") and self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].value == "(":
            self._advance()
            arguments = self._parse_call_arguments()
            if not 1 <= len(arguments) <= 3:
                self._error("range() needs one, two, or three arguments")
            if len(arguments) == 1:
                start, stop, step = NumberLiteral(0), arguments[0], NumberLiteral(1)
            elif len(arguments) == 2:
                start, stop, step = arguments[0], arguments[1], NumberLiteral(1)
            else:
                start, stop, step = arguments
            if not isinstance(step, NumberLiteral) or not isinstance(step.value, int) or step.value <= 0:
                self._error("Only positive integer range() steps are supported")
            initializer = Assignment(Identifier(name), start)
            condition = BinaryOperation(Identifier(name), "<", stop)
            update = Assignment(Identifier(name), BinaryOperation(Identifier(name), "+", step))
            return ForStatement(initializer, condition, update, self._parse_suite())
        return ForEachStatement(name, self._parse_expression(), self._parse_suite())

    def _looks_like_brace_foreach(self) -> bool:
        position = self.position
        if position < len(self.tokens) and self.tokens[position].value in self.declaration_keywords:
            position += 1
        return (
            position + 1 < len(self.tokens)
            and self.tokens[position].type == "IDENTIFIER"
            and self.tokens[position + 1].type == "SYMBOL"
            and self.tokens[position + 1].value == ":"
        )

    def _parse_do_while(self) -> DoWhileStatement:
        self._advance()  # do
        body = self._parse_suite()
        self._expect("KEYWORD", "while", "Expected 'while' after do block")
        self._expect("SYMBOL", "(", "Expected '(' after 'while'")
        condition = self._parse_expression()
        self._expect("SYMBOL", ")", "Expected ')' after do-while condition")
        self._expect("SYMBOL", ";", "Expected ';' after do-while statement")
        return DoWhileStatement(body, condition)

    def _parse_switch(self) -> SwitchStatement:
        """Parse C++/Java ``switch (value) { case ...: ... }`` syntax."""
        self._advance()  # switch
        self._expect("SYMBOL", "(", "Expected '(' after 'switch'")
        expression = self._parse_expression()
        self._expect("SYMBOL", ")", "Expected ')' after switch expression")
        self._expect("SYMBOL", "{", "Expected '{' to start switch")
        cases: list[SwitchCase] = []
        has_default = False
        self._skip_newlines()
        while not self._matches("SYMBOL", "}"):
            if self.current is None:
                self._error("Expected '}' to close switch")
            if self._match("KEYWORD", "case") is not None:
                value = self._parse_expression()
                self._expect("SYMBOL", ":", "Expected ':' after case value")
            elif self._match("KEYWORD", "default") is not None:
                if has_default:
                    self._error("A switch statement may have only one default branch")
                has_default = True
                value = None
                self._expect("SYMBOL", ":", "Expected ':' after 'default'")
            else:
                self._error("Expected 'case' or 'default' in switch")
            statements = self._parse_switch_case_statements()
            cases.append(SwitchCase(value, Block(statements)))
        self._expect("SYMBOL", "}", "Expected '}' to close switch")
        return SwitchStatement(expression, cases, fall_through=True)

    def _parse_switch_case_statements(self) -> list[Statement]:
        statements: list[Statement] = []
        self._skip_newlines()
        while self.current is not None and not self._matches("SYMBOL", "}"):
            if self._matches("KEYWORD", "case") or self._matches("KEYWORD", "default"):
                break
            statements.append(self._parse_statement())
            self._skip_newlines()
        return statements

    def _parse_match(self) -> SwitchStatement:
        """Parse Python ``match value: case value: ...`` syntax without fall-through."""
        self._advance()  # match
        expression = self._parse_expression()
        self._expect("SYMBOL", ":", "Expected ':' after match expression")
        self._expect("NEWLINE", message="Expected newline after match expression")
        self._expect("INDENT", message="Expected an indented match block")
        cases: list[SwitchCase] = []
        has_default = False
        while not self._matches("DEDENT"):
            self._expect("KEYWORD", "case", "Expected 'case' in match block")
            if self._matches("IDENTIFIER", "_"):
                if has_default:
                    self._error("A match statement may have only one default case")
                has_default = True
                self._advance()
                value = None
            else:
                value = self._parse_expression()
            body = self._parse_suite()
            cases.append(SwitchCase(value, body))
        self._expect("DEDENT", message="Expected end of match block")
        return SwitchStatement(expression, cases, fall_through=False)

    def _parse_try(self) -> TryStatement:
        """Parse one simplified ``try/catch`` or ``try/except`` pair."""
        self._advance()  # try
        try_branch = self._parse_suite()
        handler_keyword = "catch" if self.style == "brace" else "except"
        self._expect("KEYWORD", handler_keyword, f"Expected '{handler_keyword}' after try block")
        except_branch = self._parse_suite()
        return TryStatement(try_branch, except_branch)

    def _parse_function(self, *, is_static: bool = False) -> FunctionDeclaration:
        if self.style == "indent":
            self._advance()  # 'def'
            return_type = None
        else:
            return_type = str(self._advance().value)

        name = str(self._expect("IDENTIFIER", message="Expected function name").value)
        self._expect("SYMBOL", "(", "Expected '(' after function name")
        parameters: list[str] = []
        parameter_types: list[str] = []
        parameter_by_reference: list[bool] = []
        if not self._matches("SYMBOL", ")"):
            while True:
                if self.style == "brace":
                    if self.current is None or self.current.value not in self.declaration_keywords:
                        self._error("Expected parameter type")
                    parameter_types.append(str(self._advance().value))
                    parameter_by_reference.append(self._match("OP", "&") is not None)
                    if self._match("SYMBOL", "[") is not None:
                        self._expect("SYMBOL", "]", "Expected ']' after parameter array type")
                parameter = self._expect("IDENTIFIER", message="Expected parameter name")
                parameters.append(str(parameter.value))
                if self.style == "indent":
                    parameter_by_reference.append(False)
                if self._match("SYMBOL", ",") is None:
                    break
        self._expect("SYMBOL", ")", "Expected ')' after parameters")
        return FunctionDeclaration(name, parameters, self._parse_suite(), return_type, is_static, parameter_types, parameter_by_reference)

    def _parse_constructor(self, class_name: str) -> FunctionDeclaration:
        """Parse a Java/C++ constructor, which has no declared return type."""
        self._expect("IDENTIFIER", class_name, f"Expected constructor name {class_name!r}")
        self._expect("SYMBOL", "(", "Expected '(' after constructor name")
        parameters: list[str] = []
        if not self._matches("SYMBOL", ")"):
            while True:
                if self.current is None or self.current.value not in self.declaration_keywords:
                    self._error("Expected constructor parameter type")
                self._advance()
                parameter = self._expect("IDENTIFIER", message="Expected constructor parameter name")
                parameters.append(str(parameter.value))
                if self._match("SYMBOL", ",") is None:
                    break
        self._expect("SYMBOL", ")", "Expected ')' after constructor parameters")
        parent_call: SuperConstructorCall | None = None
        if self.style == "brace" and self._match("SYMBOL", ":") is not None:
            # C++ base initializer subset: Child(args) : Parent(args) { ... }
            self._expect("IDENTIFIER", message="Expected parent class after ':'")
            parent_call = SuperConstructorCall(self._parse_call_arguments())
        body = self._parse_suite()
        if parent_call is not None:
            body = Block([parent_call, *body.statements])
        return FunctionDeclaration(class_name, parameters, body, return_type=None)

    def _looks_like_constructor(self, class_name: str) -> bool:
        if self.current is None or self.current.type != "IDENTIFIER" or self.current.value != class_name:
            return False
        return self.position + 1 < len(self.tokens) and self.tokens[self.position + 1].type == "SYMBOL" and self.tokens[self.position + 1].value == "("

    def _parse_class(self) -> ClassDeclaration:
        self._advance()  # 'class'
        name = str(self._expect("IDENTIFIER", message="Expected class name").value)
        parent_name = None
        if self.style == "brace" and self._match("KEYWORD", "extends") is not None:
            parent_name = str(self._expect("IDENTIFIER", message="Expected parent class after 'extends'").value)
        elif self.style == "brace" and self._match("SYMBOL", ":") is not None:
            parent_name = str(self._expect("IDENTIFIER", message="Expected parent class after ':'").value)
        self._expect("SYMBOL", "{", "Expected '{' after class name")
        attributes: list[VariableDeclaration] = []
        static_attributes: list[VariableDeclaration] = []
        methods: list[FunctionDeclaration] = []
        constructors: list[FunctionDeclaration] = []

        while not self._matches("SYMBOL", "}"):
            if self.current is None:
                self._error("Expected '}' to close class")
            is_static = self.style == "brace" and self._match("KEYWORD", "static") is not None
            if self._looks_like_typed_function():
                methods.append(self._parse_function(is_static=is_static))
                continue
            if self._looks_like_constructor(name):
                if is_static:
                    self._error("Constructors cannot be static")
                constructors.append(self._parse_constructor(name))
                continue
            statement = self._parse_assignment_or_declaration()
            if not isinstance(statement, VariableDeclaration):
                self._error("Only attributes and methods are supported in a class body")
            (static_attributes if is_static else attributes).append(statement)

        self._expect("SYMBOL", "}")
        self._match("SYMBOL", ";")  # Required after C++ class declarations, optional for Java.
        if len(constructors) > 1:
            self._error(f"Class {name!r} may declare only one constructor in this subset")
        return ClassDeclaration(name, attributes, methods, constructors, parent_name, static_attributes)

    def _parse_return(self) -> ReturnStatement:
        self._advance()  # 'return'
        if self.style == "brace" and self._matches("SYMBOL", ";"):
            self._advance()
            return ReturnStatement()
        if self.style == "indent" and self._matches("NEWLINE"):
            self._advance()
            return ReturnStatement()

        value = self._parse_expression()
        self._finish_simple_statement()
        return ReturnStatement(value)

    def _parse_array_initializer(self) -> list[Expression]:
        """Parse ``{a, b}`` in brace languages or ``[a, b]`` in Python."""
        opening = "{" if self.style == "brace" and self._matches("SYMBOL", "{") else "["
        closing = "}" if opening == "{" else "]"
        self._expect("SYMBOL", opening, "Expected array initializer")
        values: list[Expression] = []
        if not self._matches("SYMBOL", closing):
            while True:
                values.append(self._parse_expression())
                if self._match("SYMBOL", ",") is None:
                    break
        self._expect("SYMBOL", closing, "Expected end of array initializer")
        return values

    def _parse_import(self) -> ImportStatement:
        self._advance()
        module = str(self._expect("IDENTIFIER", message="Expected module name after 'import'").value)
        self._finish_simple_statement()
        return ImportStatement(module)

    def _parse_with_file(self) -> WithFileStatement:
        self._advance()
        resource = self._parse_expression()
        self._expect("KEYWORD", "as", "Expected 'as' after with resource")
        name = str(self._expect("IDENTIFIER", message="Expected variable name after 'as'").value)
        return WithFileStatement(resource, name, self._parse_suite())

    def _parse_suite(self) -> Block:
        if self.style == "brace":
            self._expect("SYMBOL", "{", "Expected '{' to start block")
            statements = self._parse_statements_until(end_symbol="}")
            self._expect("SYMBOL", "}", "Expected '}' to close block")
            return Block(statements)

        self._expect("SYMBOL", ":", "Expected ':' to start Python block")
        self._expect("NEWLINE", message="Expected newline after ':'")
        self._expect("INDENT", message="Expected an indented Python block")
        statements = self._parse_statements_until(end_symbol=None)
        self._expect("DEDENT", message="Expected end of indented Python block")
        return Block(statements)

    def _parse_expression(self, minimum_precedence: int = 1) -> Expression:
        left = self._parse_unary()
        return self._parse_binary_expression(left, minimum_precedence)

    def _parse_binary_expression(self, left: Expression, minimum_precedence: int = 1) -> Expression:
        while self.current is not None:
            operator = str(self.current.value)
            precedence = self._PRECEDENCE.get(operator, 0)
            if precedence < minimum_precedence:
                break
            self._advance()
            right = self._parse_expression(precedence + 1)
            left = BinaryOperation(left, operator, right)
        return left

    def _parse_unary(self) -> Expression:
        if self._matches("OP") and self.current.value in {"-", "!"}:
            operator = str(self._advance().value)
            return UnaryOperation(operator, self._parse_unary())
        if self._matches("KEYWORD", "not"):
            self._advance()
            return UnaryOperation("not", self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> Expression:
        if self._matches("NUMBER"):
            return self._parse_postfix(NumberLiteral(self._advance().value))  # type: ignore[arg-type]
        if self._matches("STRING"):
            return self._parse_postfix(StringLiteral(str(self._advance().value)))
        if self._matches("SYMBOL", "["):
            if self.style == "indent":
                return self._parse_postfix(self._parse_python_list_or_comprehension())
            return self._parse_postfix(ListLiteral(self._parse_array_initializer()))
        if self.style == "indent" and self._matches("SYMBOL", "{"):
            return self._parse_postfix(self._parse_python_mapping_or_set())
        if self.style == "brace" and self._matches("SYMBOL", "{"):
            return self._parse_postfix(ListLiteral(self._parse_array_initializer()))
        if self.current is not None and str(self.current.value) in self._BOOLEAN_VALUES:
            return self._parse_postfix(BooleanLiteral(self._BOOLEAN_VALUES[str(self._advance().value)]))
        if self.current is not None and str(self.current.value) in {"None", "null", "nullptr"}:
            self._advance()
            return self._parse_postfix(NullLiteral())
        if self._matches("KEYWORD", "new"):
            self._advance()
            class_name = str(self._expect("IDENTIFIER", message="Expected class name after 'new'").value)
            return self._parse_postfix(NewExpression(class_name, self._parse_call_arguments()))
        if self._matches("IDENTIFIER") or self._matches("KEYWORD", "this") or self._matches("KEYWORD", "self"):
            return self._parse_postfix(Identifier(str(self._advance().value)))
        if self._match("SYMBOL", "(") is not None:
            if self.style == "indent" and self._match("SYMBOL", ")") is not None:
                return self._parse_postfix(TupleLiteral([]))
            expression = self._parse_expression()
            if self.style == "indent" and self._match("SYMBOL", ",") is not None:
                elements = [expression]
                while not self._matches("SYMBOL", ")"):
                    elements.append(self._parse_expression())
                    if self._match("SYMBOL", ",") is None:
                        break
                self._expect("SYMBOL", ")", "Expected ')' after tuple literal")
                return self._parse_postfix(TupleLiteral(elements))
            self._expect("SYMBOL", ")", "Expected ')' after expression")
            return self._parse_postfix(expression)
        self._error("Expected a number, string, variable, or parenthesized expression")

    def _parse_python_mapping_or_set(self) -> Expression:
        """Parse ``{key: value}``, ``{value}``, and an empty dictionary."""
        self._expect("SYMBOL", "{")
        if self._match("SYMBOL", "}") is not None:
            return MappingLiteral([])
        first = self._parse_expression()
        if self._match("SYMBOL", ":") is not None:
            entries = [(first, self._parse_expression())]
            while self._match("SYMBOL", ",") is not None:
                if self._matches("SYMBOL", "}"):
                    break
                key = self._parse_expression()
                self._expect("SYMBOL", ":", "Expected ':' after dictionary key")
                entries.append((key, self._parse_expression()))
            self._expect("SYMBOL", "}", "Expected '}' after dictionary literal")
            return MappingLiteral(entries)
        elements = [first]
        while self._match("SYMBOL", ",") is not None:
            if self._matches("SYMBOL", "}"):
                break
            elements.append(self._parse_expression())
        self._expect("SYMBOL", "}", "Expected '}' after set literal")
        return SetLiteral(elements)

    def _parse_python_list_or_comprehension(self) -> Expression:
        self._expect("SYMBOL", "[")
        if self._match("SYMBOL", "]") is not None:
            return ListLiteral([])
        first = self._parse_expression()
        if self._match("KEYWORD", "for") is not None:
            name = str(self._expect("IDENTIFIER", message="Expected variable in list comprehension").value)
            self._expect("KEYWORD", "in", "Expected 'in' in list comprehension")
            iterable = self._parse_expression()
            self._expect("SYMBOL", "]", "Expected ']' after list comprehension")
            return ListComprehension(first, name, iterable)
        values = [first]
        while self._match("SYMBOL", ",") is not None:
            if self._matches("SYMBOL", "]"):
                break
            values.append(self._parse_expression())
        self._expect("SYMBOL", "]", "Expected ']' after list literal")
        return ListLiteral(values)

    def _parse_postfix(self, expression: Expression) -> Expression:
        while True:
            if self._match("DOT") is not None:
                member = self._expect("IDENTIFIER", message="Expected member name after '.'")
                expression = MemberAccess(expression, str(member.value))
            elif self._match("SYMBOL", "[") is not None:
                index = self._parse_expression()
                self._expect("SYMBOL", "]", "Expected ']' after array index")
                expression = IndexAccess(expression, index)
            elif self._matches("SYMBOL", "("):
                expression = CallExpression(expression, self._parse_call_arguments())
            else:
                return expression

    def _parse_call_arguments(self) -> list[Expression]:
        self._expect("SYMBOL", "(", "Expected '('")
        arguments: list[Expression] = []
        if not self._matches("SYMBOL", ")"):
            while True:
                arguments.append(self._parse_expression())
                if self._match("SYMBOL", ",") is None:
                    break
        self._expect("SYMBOL", ")", "Expected ')' after arguments")
        return arguments
