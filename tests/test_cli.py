"""Tests for user-facing CLI errors that should not expose Python tracebacks."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import main


class CliTests(unittest.TestCase):
    def test_missing_native_source_has_a_clear_error(self) -> None:
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["main.py", "--lang", "java", "--engine", "native", "missing.java"]):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as exit_info:
                    main.main()
        self.assertEqual(exit_info.exception.code, 2)
        self.assertIn("Native execution failed: Source file not found: missing.java", stderr.getvalue())

    def test_missing_evaluator_source_has_a_clear_error(self) -> None:
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["main.py", "--lang", "python", "missing.py"]):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as exit_info:
                    main.main()
        self.assertEqual(exit_info.exception.code, 2)
        self.assertIn("Source file not found: missing.py", stderr.getvalue())

    def test_check_mode_requires_cpp_include_and_main(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = f"{temporary_directory}/program.cpp"
            with open(source, "w", encoding="utf-8") as file:
                file.write("int value = 3;")
            with patch.object(sys, "argv", ["main.py", "--lang", "cpp", "--check", source]):
                result = main.main()
        self.assertEqual(result, 1)

    def test_syntax_error_shows_source_line_and_caret(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = f"{temporary_directory}/broken.py"
            with open(source, "w", encoding="utf-8") as file:
                file.write("value = @\n")
            with patch.object(sys, "argv", ["main.py", "--lang", "python", source]), redirect_stderr(stderr):
                result = main.main()
        self.assertEqual(result, 1)
        self.assertIn("Syntax error: Unexpected character '@' at line 1, column 9", stderr.getvalue())
        self.assertIn("1 | value = @", stderr.getvalue())
        self.assertIn("^", stderr.getvalue())

    def test_syntax_report_collects_multiple_independent_errors(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = f"{temporary_directory}/broken.py"
            with open(source, "w", encoding="utf-8") as file:
                file.write("first =\nsecond =\nprint(1)\n")
            with patch.object(sys, "argv", ["main.py", "--lang", "python", "--syntax-report", source]), redirect_stderr(stderr):
                result = main.main()
        self.assertEqual(result, 1)
        report = stderr.getvalue()
        self.assertIn("Syntax errors found: 2", report)
        self.assertIn("1 | first =", report)
        self.assertIn("2 | second =", report)
        self.assertIn("Hint: Add an expression after '=' or the operator", report)

    def test_syntax_diagnostic_suggests_missing_python_colon(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = f"{temporary_directory}/missing_colon.py"
            with open(source, "w", encoding="utf-8") as file:
                file.write("if True\n    print(1)\n")
            with patch.object(sys, "argv", ["main.py", "--lang", "python", source]), redirect_stderr(stderr):
                result = main.main()
        self.assertEqual(result, 1)
        self.assertIn("Expected ':'", stderr.getvalue())
        self.assertIn("Hint: Add ':' after the Python block header", stderr.getvalue())

    def test_recursive_overflow_uses_structured_runtime_diagnostic(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = f"{temporary_directory}/recursive.py"
            with open(source, "w", encoding="utf-8") as file:
                file.write("def loop():\n    return loop()\nvalue = loop()\n")
            with patch.object(sys, "argv", ["main.py", "--lang", "python", "--max-call-depth", "3", source]), redirect_stderr(stderr):
                result = main.main()
        self.assertEqual(result, 1)
        self.assertIn("Runtime error [CALL_DEPTH]", stderr.getvalue())
        self.assertIn("loop() -> loop()", stderr.getvalue())

    def test_cpp_include_main_and_array_literal_execute_together(self) -> None:
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = f"{temporary_directory}/complete.cpp"
            with open(source, "w", encoding="utf-8") as file:
                file.write(
                    "#include <iostream>\n"
                    "int main() { int items[] = {1, 2, 3}; int total = 0; "
                    "for (int index = 0; index < items.length(); index++) { total += items[index]; } "
                    "print(total); return 0; }\n"
                )
            with patch.object(sys, "argv", ["main.py", "--lang", "cpp", source]), redirect_stderr(io.StringIO()):
                with redirect_stdout(stdout):
                    result = main.main()
        self.assertEqual(result, 0)
        self.assertIn("6", stdout.getvalue())
        self.assertIn("Execution completed.", stdout.getvalue())

    def test_java_public_class_and_standard_main_execute_together(self) -> None:
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = f"{temporary_directory}/Main.java"
            with open(source, "w", encoding="utf-8") as file:
                file.write(
                    "public class Main { public static void main(String[] args) { "
                    "int items[] = {1, 2, 3}; int total = 0; "
                    "for (int index = 0; index < items.length(); index++) { total += items[index]; } "
                    "print(total); } }\n"
                )
            with patch.object(sys, "argv", ["main.py", "--lang", "java", source]), redirect_stderr(io.StringIO()):
                with redirect_stdout(stdout):
                    result = main.main()
        self.assertEqual(result, 0)
        self.assertIn("6", stdout.getvalue())

    def test_evaluator_rejects_incomplete_cpp_and_java_files(self) -> None:
        for suffix, language, text in (
            (".cpp", "cpp", "int value = 3;"),
            (".java", "java", "class Main { void main() { } }"),
        ):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temporary_directory:
                source = f"{temporary_directory}/Main{suffix}"
                with open(source, "w", encoding="utf-8") as file:
                    file.write(text)
                with patch.object(sys, "argv", ["main.py", "--lang", language, source]), redirect_stderr(io.StringIO()):
                    self.assertEqual(main.main(), 1)


if __name__ == "__main__":
    unittest.main()
