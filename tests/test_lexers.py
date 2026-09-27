"""Tests showing expected token streams for all three Phase 1 lexers."""

import unittest

from frontends.cpp_lexer import lex_cpp
from frontends.java_lexer import lex_java
from frontends.python_lexer import lex_python
from frontends.tokens import Token


class CppLexerTests(unittest.TestCase):
    def test_cpp_types_arithmetic_and_braces(self) -> None:
        tokens = lex_cpp("int total = 10 + 5; { total = total * 2; }")
        self.assertEqual(
            [(token.type, token.value) for token in tokens],
            [
                ("KEYWORD", "int"), ("IDENTIFIER", "total"), ("ASSIGN", "="),
                ("NUMBER", 10), ("OP", "+"), ("NUMBER", 5), ("SYMBOL", ";"),
                ("SYMBOL", "{"), ("IDENTIFIER", "total"), ("ASSIGN", "="),
                ("IDENTIFIER", "total"), ("OP", "*"), ("NUMBER", 2), ("SYMBOL", ";"),
                ("SYMBOL", "}"),
            ],
        )

    def test_cpp_string_and_input_operator(self) -> None:
        tokens = lex_cpp('string prompt = "Age: "; cin >> age;')
        self.assertEqual(
            [(token.type, token.value) for token in tokens],
            [
                ("KEYWORD", "string"), ("IDENTIFIER", "prompt"), ("ASSIGN", "="),
                ("STRING", "Age: "), ("SYMBOL", ";"), ("IDENTIFIER", "cin"),
                ("OP", ">>"), ("IDENTIFIER", "age"), ("SYMBOL", ";"),
            ],
        )

    def test_cpp_compound_and_increment_operators(self) -> None:
        self.assertEqual(
            [(token.type, token.value) for token in lex_cpp("score += 2; score++; score--; ")],
            [
                ("IDENTIFIER", "score"), ("OP", "+="), ("NUMBER", 2), ("SYMBOL", ";"),
                ("IDENTIFIER", "score"), ("OP", "++"), ("SYMBOL", ";"),
                ("IDENTIFIER", "score"), ("OP", "--"), ("SYMBOL", ";"),
            ],
        )

    def test_cpp_include_is_accepted_without_affecting_source_line_numbers(self) -> None:
        tokens = lex_cpp("#include <iostream>\nint value = 7;")
        self.assertEqual(
            [(token.type, token.value, token.line) for token in tokens],
            [
                ("KEYWORD", "int", 2), ("IDENTIFIER", "value", 2),
                ("ASSIGN", "=", 2), ("NUMBER", 7, 2), ("SYMBOL", ";", 2),
            ],
        )


class PythonLexerTests(unittest.TestCase):
    def test_python_indentation_and_newlines(self) -> None:
        tokens = lex_python("if score > 5:\n    total = score + 1\n")
        self.assertEqual(
            [(token.type, token.value) for token in tokens],
            [
                ("KEYWORD", "if"), ("IDENTIFIER", "score"), ("OP", ">"),
                ("NUMBER", 5), ("SYMBOL", ":"), ("NEWLINE", "\\n"),
                ("INDENT", 4), ("IDENTIFIER", "total"), ("ASSIGN", "="),
                ("IDENTIFIER", "score"), ("OP", "+"), ("NUMBER", 1),
                ("NEWLINE", "\\n"), ("DEDENT", 0),
            ],
        )

    def test_python_string_literal(self) -> None:
        self.assertEqual(
            [(token.type, token.value) for token in lex_python('message = "Hello, Ada"\n')],
            [("IDENTIFIER", "message"), ("ASSIGN", "="), ("STRING", "Hello, Ada"), ("NEWLINE", "\\n")],
        )

    def test_python_compound_assignment(self) -> None:
        self.assertEqual(
            [(token.type, token.value) for token in lex_python("score += 2\n")],
            [("IDENTIFIER", "score"), ("OP", "+="), ("NUMBER", 2), ("NEWLINE", "\\n")],
        )


class JavaLexerTests(unittest.TestCase):
    def test_java_class_and_dot_notation(self) -> None:
        tokens = lex_java("class Counter { int value = 0; this.value = 1; }")
        self.assertEqual(
            [(token.type, token.value) for token in tokens],
            [
                ("KEYWORD", "class"), ("IDENTIFIER", "Counter"), ("SYMBOL", "{"),
                ("KEYWORD", "int"), ("IDENTIFIER", "value"), ("ASSIGN", "="),
                ("NUMBER", 0), ("SYMBOL", ";"), ("KEYWORD", "this"), ("DOT", "."),
                ("IDENTIFIER", "value"), ("ASSIGN", "="), ("NUMBER", 1),
                ("SYMBOL", ";"), ("SYMBOL", "}"),
            ],
        )

    def test_java_public_class_and_static_main_wrapper_are_accepted(self) -> None:
        tokens = lex_java(
            "public class Main { public static void main(String[] args) { print(7); } }"
        )
        self.assertEqual(
            [(token.type, token.value) for token in tokens[:9]],
            [
                ("KEYWORD", "class"), ("IDENTIFIER", "Main"), ("SYMBOL", "{"),
                ("KEYWORD", "static"), ("KEYWORD", "void"), ("IDENTIFIER", "main"),
                ("SYMBOL", "("), ("KEYWORD", "String"), ("SYMBOL", "["),
            ],
        )


class ErrorTests(unittest.TestCase):
    def test_invalid_character_has_source_position(self) -> None:
        with self.assertRaisesRegex(SyntaxError, r"Unexpected character '@' at line 1, column 7"):
            lex_cpp("value @ 3")


if __name__ == "__main__":
    unittest.main()
