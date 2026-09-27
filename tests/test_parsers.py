"""Phase 2 tests for AST construction and expression precedence."""

import unittest

from core.ast_nodes import (
    Assignment,
    ArrayDeclaration,
    BinaryOperation,
    BreakStatement,
    ContinueStatement,
    FunctionDeclaration,
    ForStatement,
    IfStatement,
    ReturnStatement,
    InputStatement,
    StringLiteral,
    SwitchStatement,
    TryStatement,
    DoWhileStatement,
    ForEachStatement,
    IndexAccess,
    ListLiteral,
    VariableDeclaration,
    WhileStatement,
)
from frontends.cpp_lexer import lex_cpp
from frontends.cpp_parser import parse_cpp
from frontends.cpp_parser import parse_cpp_recovering
from frontends.java_lexer import lex_java
from frontends.java_parser import parse_java
from frontends.python_lexer import lex_python
from frontends.python_parser import parse_python
from frontends.python_parser import parse_python_recovering


class ParserTests(unittest.TestCase):
    def test_recovery_parser_collects_independent_cpp_errors(self) -> None:
        _, diagnostics = parse_cpp_recovering(lex_cpp(
            'int main() { int first = ; int second = ; return 0; }'
        ))
        self.assertEqual(len(diagnostics), 2)
        self.assertEqual([item.line for item in diagnostics], [1, 1])

    def test_recovery_parser_collects_independent_python_errors(self) -> None:
        _, diagnostics = parse_python_recovering(lex_python('first =\nsecond =\nprint(1)\n'))
        self.assertEqual(len(diagnostics), 2)
        self.assertEqual([item.line for item in diagnostics], [1, 2])
    def test_cpp_declaration_precedence_if_else_and_while(self) -> None:
        program = parse_cpp(lex_cpp(
            "int result = 10 + 5 * 2; "
            "if (result > 15) { result = result - 1; } else { result = 0; } "
            "while (result > 0) { result = result - 1; }"
        ))

        declaration, conditional, loop = program.statements
        self.assertIsInstance(declaration, VariableDeclaration)
        self.assertEqual(declaration.declared_type, "int")
        self.assertIsInstance(declaration.value, BinaryOperation)
        self.assertEqual(declaration.value.operator, "+")
        self.assertIsInstance(declaration.value.right, BinaryOperation)
        self.assertEqual(declaration.value.right.operator, "*")
        self.assertIsInstance(conditional, IfStatement)
        self.assertIsNotNone(conditional.else_branch)
        self.assertIsInstance(loop, WhileStatement)

    def test_python_indented_if_else_and_while(self) -> None:
        program = parse_python(lex_python(
            "score = 10 + 5 * 2\n"
            "if score > 15:\n"
            "    score = score - 1\n"
            "else:\n"
            "    score = 0\n"
            "while score > 0:\n"
            "    score = score - 1\n"
        ))

        assignment, conditional, loop = program.statements
        self.assertIsInstance(assignment, Assignment)
        self.assertIsInstance(assignment.value, BinaryOperation)
        self.assertEqual(assignment.value.right.operator, "*")
        self.assertIsInstance(conditional, IfStatement)
        self.assertEqual(len(conditional.then_branch.statements), 1)
        self.assertIsNotNone(conditional.else_branch)
        self.assertIsInstance(loop, WhileStatement)

    def test_java_typed_assignment_and_brace_if(self) -> None:
        program = parse_java(lex_java(
            "int score = 4; if (score == 4) { score = score + 1; }"
        ))

        declaration, conditional = program.statements
        self.assertIsInstance(declaration, VariableDeclaration)
        self.assertEqual(declaration.declared_type, "int")
        self.assertIsInstance(conditional, IfStatement)
        self.assertEqual(conditional.condition.operator, "==")

    def test_missing_statement_terminator_is_rejected(self) -> None:
        with self.assertRaisesRegex(SyntaxError, "Expected ';' after statement"):
            parse_cpp(lex_cpp("int score = 5"))

    def test_function_declarations_and_returns(self) -> None:
        cpp_program = parse_cpp(lex_cpp("int add(int left, int right) { return left + right; }"))
        cpp_function = cpp_program.statements[0]
        self.assertIsInstance(cpp_function, FunctionDeclaration)
        self.assertEqual(cpp_function.parameters, ["left", "right"])
        self.assertIsInstance(cpp_function.body.statements[0], ReturnStatement)

        python_program = parse_python(lex_python("def add(left, right):\n    return left + right\n"))
        python_function = python_program.statements[0]
        self.assertIsInstance(python_function, FunctionDeclaration)
        self.assertIsNone(python_function.return_type)
        self.assertEqual(python_function.parameters, ["left", "right"])

    def test_cpp_cin_statement_and_python_string_expression(self) -> None:
        cpp_program = parse_cpp(lex_cpp("int age; cin >> age;"))
        self.assertIsInstance(cpp_program.statements[1], InputStatement)

        python_program = parse_python(lex_python('message = "hello"\n'))
        assignment = python_program.statements[0]
        self.assertIsInstance(assignment, Assignment)
        self.assertIsInstance(assignment.value, StringLiteral)

    def test_cpp_java_and_python_for_loops(self) -> None:
        cpp_loop = parse_cpp(lex_cpp(
            "for (int index = 0; index < 3; index = index + 1) { value = index; }"
        )).statements[0]
        java_loop = parse_java(lex_java(
            "for (int index = 0; index < 3; index = index + 1) { value = index; }"
        )).statements[0]
        python_loop = parse_python(lex_python(
            "for index in range(3):\n    value = index\n"
        )).statements[0]
        self.assertIsInstance(cpp_loop, ForStatement)
        self.assertIsInstance(java_loop, ForStatement)
        self.assertIsInstance(python_loop, ForStatement)

    def test_array_declarations_list_literals_and_indexes(self) -> None:
        cpp_array = parse_cpp(lex_cpp("int marks[2] = {70, 80}; marks[0] = 75;")).statements
        java_array = parse_java(lex_java("int[] marks = {70, 80}; marks[0] = 75;")).statements
        python_array = parse_python(lex_python("marks = [70, 80]\nmarks[0] = 75\n")).statements
        self.assertIsInstance(cpp_array[0], ArrayDeclaration)
        self.assertIsInstance(java_array[0], ArrayDeclaration)
        self.assertIsInstance(python_array[0], Assignment)
        self.assertIsInstance(python_array[0].value, ListLiteral)
        self.assertIsInstance(cpp_array[1], Assignment)
        self.assertIsInstance(cpp_array[1].target, IndexAccess)

    def test_break_and_continue_statements_parse(self) -> None:
        cpp = parse_cpp(lex_cpp("while (true) { continue; break; }")).statements[0]
        java = parse_java(lex_java("while (true) { continue; break; }")).statements[0]
        python = parse_python(lex_python("while True:\n    continue\n    break\n")).statements[0]
        for loop in (cpp, java, python):
            self.assertIsInstance(loop, WhileStatement)
            self.assertIsInstance(loop.body.statements[0], ContinueStatement)
            self.assertIsInstance(loop.body.statements[1], BreakStatement)

    def test_else_if_and_elif_create_nested_conditional_branches(self) -> None:
        brace = parse_cpp(lex_cpp(
            "if (score > 90) { result = 1; } else if (score > 70) { result = 2; } else { result = 3; }"
        )).statements[0]
        python = parse_python(lex_python(
            "if score > 90:\n    result = 1\nelif score > 70:\n    result = 2\nelse:\n    result = 3\n"
        )).statements[0]
        for conditional in (brace, python):
            self.assertIsInstance(conditional, IfStatement)
            self.assertIsNotNone(conditional.else_branch)
            self.assertIsInstance(conditional.else_branch.statements[0], IfStatement)

    def test_switch_and_match_parse_into_multi_way_branch_nodes(self) -> None:
        brace = parse_cpp(lex_cpp(
            "switch (day) { case 1: result = 1; break; default: result = 0; }"
        )).statements[0]
        python = parse_python(lex_python(
            "match day:\n    case 1:\n        result = 1\n    case _:\n        result = 0\n"
        )).statements[0]
        self.assertIsInstance(brace, SwitchStatement)
        self.assertTrue(brace.fall_through)
        self.assertEqual(len(brace.cases), 2)
        self.assertIsInstance(python, SwitchStatement)
        self.assertFalse(python.fall_through)
        self.assertIsNone(python.cases[1].value)

    def test_try_catch_and_try_except_parse(self) -> None:
        brace = parse_cpp(lex_cpp("try { value = 10 / 0; } catch { value = 1; }")).statements[0]
        python = parse_python(lex_python(
            "try:\n    value = 10 / 0\nexcept:\n    value = 1\n"
        )).statements[0]
        self.assertIsInstance(brace, TryStatement)
        self.assertIsInstance(python, TryStatement)
        self.assertEqual(len(brace.try_branch.statements), 1)
        self.assertEqual(len(python.except_branch.statements), 1)

    def test_foreach_and_do_while_parse(self) -> None:
        brace = parse_cpp(lex_cpp(
            "for (int value : values) { total += value; } do { total++; } while (total < 3);"
        )).statements
        python = parse_python(lex_python("for value in values:\n    total += value\n")).statements[0]
        self.assertIsInstance(brace[0], ForEachStatement)
        self.assertIsInstance(brace[1], DoWhileStatement)
        self.assertIsInstance(python, ForEachStatement)


if __name__ == "__main__":
    unittest.main()
