"""Tests for complete-file structure validation and compatibility reports."""

import unittest

from core.validator import validate_source


class ValidatorTests(unittest.TestCase):
    def test_complete_cpp_program_is_structurally_valid_but_not_subset_executable(self) -> None:
        result = validate_source(
            "cpp",
            "#include <iostream>\n"
            "int main() { int value = 3; if (value > 0) { std::cout << value; } return 0; }\n",
            "main.cpp",
        )
        self.assertTrue(result.structurally_valid)
        self.assertFalse(result.evaluator_compatible)

    def test_include_and_evaluator_subset_main_are_compatible(self) -> None:
        result = validate_source(
            "cpp",
            "#include <iostream>\nint main() { int values[] = {1, 2}; print(values[0]); return 0; }\n",
            "main.cpp",
        )
        self.assertTrue(result.structurally_valid)
        self.assertTrue(result.evaluator_compatible)

    def test_cpp_reports_missing_include_and_main(self) -> None:
        result = validate_source("cpp", "int value = 3;")
        self.assertFalse(result.structurally_valid)
        self.assertEqual({diagnostic.code for diagnostic in result.diagnostics if diagnostic.kind == "error"}, {"CPP_INCLUDE", "CPP_MAIN"})

    def test_complete_java_program_checks_filename_and_main(self) -> None:
        source = (
            "public class Main { public static void main(String[] args) { "
            "System.out.println(\"ready\"); } }"
        )
        valid = validate_source("java", source, "Main.java")
        wrong_filename = validate_source("java", source, "Program.java")
        self.assertTrue(valid.structurally_valid)
        self.assertTrue(valid.evaluator_compatible)
        self.assertFalse(wrong_filename.structurally_valid)
        self.assertTrue(any(diagnostic.code == "JAVA_FILENAME" for diagnostic in wrong_filename.diagnostics))

    def test_java_requires_a_public_class_for_complete_file_validation(self) -> None:
        result = validate_source(
            "java", "class Main { public static void main(String[] args) { } }", "Main.java"
        )
        self.assertFalse(result.structurally_valid)
        self.assertTrue(any(diagnostic.code == "JAVA_PUBLIC_CLASS" for diagnostic in result.diagnostics))

    def test_python_syntax_and_supported_collection_loop_are_separate(self) -> None:
        valid = validate_source("python", "for number in [1, 2]:\n    print(number)\n")
        invalid = validate_source("python", "if True\n    print(1)\n")
        self.assertTrue(valid.structurally_valid)
        self.assertTrue(valid.evaluator_compatible)
        self.assertFalse(invalid.structurally_valid)
        self.assertEqual(invalid.diagnostics[0].code, "PYTHON_SYNTAX")

    def test_unclosed_cpp_brace_is_reported(self) -> None:
        result = validate_source("cpp", "#include <iostream>\nint main() { return 0;")
        self.assertFalse(result.structurally_valid)
        self.assertTrue(any(diagnostic.code == "DELIMITER" for diagnostic in result.diagnostics))

    def test_supported_python_collection_loop_and_try_are_compatible(self) -> None:
        result = validate_source(
            "python",
            "for value in values:\n    print(value)\ntry:\n    print(1)\nexcept:\n    print(2)\n",
        )
        self.assertTrue(result.structurally_valid)
        self.assertTrue(result.evaluator_compatible)


if __name__ == "__main__":
    unittest.main()
