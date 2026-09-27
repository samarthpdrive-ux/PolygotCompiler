"""Structural source-code validation and evaluator compatibility reporting.

This module deliberately distinguishes two questions:

1. Is a complete source file structurally well formed for its language?
2. Can the project's lightweight evaluator execute every feature it uses?

It is a project validator, not a replacement for ``g++``, ``javac``, or the
official Python interpreter.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Literal


DiagnosticKind = Literal["error", "warning", "unsupported"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One source issue, including its category and position."""

    kind: DiagnosticKind
    code: str
    message: str
    line: int = 1
    column: int = 1


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The complete result of structural and evaluator-compatibility checks."""

    language: str
    diagnostics: tuple[Diagnostic, ...]

    @property
    def structurally_valid(self) -> bool:
        return not any(diagnostic.kind == "error" for diagnostic in self.diagnostics)

    @property
    def evaluator_compatible(self) -> bool:
        return not any(diagnostic.kind == "unsupported" for diagnostic in self.diagnostics)

    def format_report(self) -> str:
        """Return a compact, CLI-ready validation report."""
        structure = "valid" if self.structurally_valid else "invalid"
        support = "supported" if self.evaluator_compatible else "contains unsupported features"
        lines = [f"Structure: {structure}", f"Evaluator compatibility: {support}"]
        for diagnostic in self.diagnostics:
            lines.append(
                f"{diagnostic.kind.upper()} [{diagnostic.code}] "
                f"line {diagnostic.line}, column {diagnostic.column}: {diagnostic.message}"
            )
        return "\n".join(lines)


def validate_source(language: str, source: str, filename: str | None = None) -> ValidationResult:
    """Validate complete source-file structure for C++, Java, or Python."""
    validators = {
        "cpp": _validate_cpp,
        "java": _validate_java,
        "python": _validate_python,
    }
    try:
        validator = validators[language]
    except KeyError as error:
        raise ValueError(f"Unsupported language {language!r}") from error
    return ValidationResult(language, tuple(validator(source, filename)))


def _validate_cpp(source: str, filename: str | None) -> list[Diagnostic]:
    diagnostics = _check_brace_language_delimiters(source, "cpp")
    first_line, first_content = _first_meaningful_line(source)
    if not re.match(r"^\s*#\s*include\s*[<\"].+[>\"]", first_content):
        diagnostics.append(Diagnostic(
            "error", "CPP_INCLUDE", "A complete C++ program must begin with an #include directive.", first_line, 1
        ))
    if not re.search(r"\bint\s+main\s*\(", source):
        diagnostics.append(Diagnostic(
            "error", "CPP_MAIN", "No int main(...) entry point was found.", 1, 1
        ))
    elif not re.search(r"\bint\s+main\s*\([^)]*\)\s*\{", source, re.DOTALL):
        diagnostics.append(Diagnostic(
            "error", "CPP_MAIN_BODY", "The main entry point must open a block with '{'.", 1, 1
        ))
    if re.search(r"\b(?:cin|cout|cerr)\b", source) and not re.search(r"#\s*include\s*<iostream>", source):
        diagnostics.append(Diagnostic(
            "error", "CPP_IOSTREAM", "cin/cout/cerr requires #include <iostream>.", 1, 1
        ))
    _report_cpp_evaluator_gaps(source, diagnostics)
    return diagnostics


def _validate_java(source: str, filename: str | None) -> list[Diagnostic]:
    diagnostics = _check_brace_language_delimiters(source, "java")
    public_classes = list(re.finditer(r"\bpublic\s+class\s+([A-Za-z_]\w*)", source))
    if not public_classes:
        diagnostics.append(Diagnostic(
            "error", "JAVA_PUBLIC_CLASS", "A complete Java program must declare one public class.", 1, 1
        ))
    if len(public_classes) > 1:
        diagnostics.append(Diagnostic("error", "JAVA_PUBLIC_CLASS", "Only one public class is allowed per source file.", 1, 1))
    if public_classes and filename is not None:
        expected = f"{public_classes[0].group(1)}.java"
        if filename != expected:
            diagnostics.append(Diagnostic(
                "error", "JAVA_FILENAME", f"Public class {public_classes[0].group(1)!r} must be in {expected!r}.",
                _line_of(source, public_classes[0].start()), 1,
            ))
    main_pattern = r"\bpublic\s+static\s+void\s+main\s*\(\s*String\s*\[\s*]\s+[A-Za-z_]\w*\s*\)"
    if not re.search(main_pattern, source):
        diagnostics.append(Diagnostic(
            "error", "JAVA_MAIN", "No public static void main(String[] args) entry point was found.", 1, 1
        ))
    _report_java_evaluator_gaps(source, diagnostics)
    return diagnostics


def _validate_python(source: str, filename: str | None) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    try:
        tree = ast.parse(source, filename=filename or "<source>")
    except SyntaxError as error:
        diagnostics.append(Diagnostic(
            "error", "PYTHON_SYNTAX", error.msg, error.lineno or 1, error.offset or 1
        ))
        return diagnostics

    unsupported_nodes = {
        ast.ImportFrom: "imports are not available in the evaluator",
    }
    for node in ast.walk(tree):
        for node_type, message in unsupported_nodes.items():
            if isinstance(node, node_type):
                diagnostics.append(Diagnostic(
                    "unsupported", "PYTHON_EVALUATOR_GAP", message,
                    getattr(node, "lineno", 1), getattr(node, "col_offset", 0) + 1,
                ))
                break
        if isinstance(node, ast.Import) and any(alias.name != "math" or alias.asname is not None for alias in node.names):
            diagnostics.append(Diagnostic(
                "unsupported", "PYTHON_EVALUATOR_GAP", "only 'import math' is available in the evaluator",
                node.lineno, node.col_offset + 1,
            ))
        if isinstance(node, ast.With):
            valid_with = all(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == "open"
                and isinstance(item.optional_vars, ast.Name)
                for item in node.items
            )
            if not valid_with:
                diagnostics.append(Diagnostic(
                    "unsupported", "PYTHON_EVALUATOR_GAP", "only 'with open(...) as name:' is available in the evaluator",
                    node.lineno, node.col_offset + 1,
                ))
    return diagnostics


def _check_brace_language_delimiters(source: str, language: str) -> list[Diagnostic]:
    """Check braces, parentheses, brackets, strings, and comments in C++/Java."""
    diagnostics: list[Diagnostic] = []
    opening = {"{": "}", "(": ")", "[": "]"}
    closing = {value: key for key, value in opening.items()}
    stack: list[tuple[str, int]] = []
    state = "normal"
    index = 0

    while index < len(source):
        character = source[index]
        next_character = source[index + 1] if index + 1 < len(source) else ""
        if state == "line_comment":
            if character == "\n":
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if character == "*" and next_character == "/":
                state = "normal"
                index += 2
            else:
                index += 1
            continue
        if state in {"single_string", "double_string"}:
            quote = "'" if state == "single_string" else '"'
            if character == "\\":
                index += 2
                continue
            if character == quote:
                state = "normal"
            index += 1
            continue

        if character == "/" and next_character == "/":
            state = "line_comment"
            index += 2
            continue
        if character == "/" and next_character == "*":
            state = "block_comment"
            index += 2
            continue
        if character == "'":
            state = "single_string"
            index += 1
            continue
        if character == '"':
            state = "double_string"
            index += 1
            continue
        if character in opening:
            stack.append((character, index))
        elif character in closing:
            if not stack or stack[-1][0] != closing[character]:
                diagnostics.append(Diagnostic(
                    "error", "DELIMITER", f"Unexpected closing delimiter {character!r}.", *_position_of(source, index)
                ))
            else:
                stack.pop()
        index += 1

    if state == "block_comment":
        diagnostics.append(Diagnostic("error", "COMMENT", "Unterminated block comment.", *_position_of(source, len(source))))
    elif state in {"single_string", "double_string"}:
        diagnostics.append(Diagnostic("error", "STRING", "Unterminated string literal.", *_position_of(source, len(source))))
    for delimiter, position in stack:
        diagnostics.append(Diagnostic(
            "error", "DELIMITER", f"Unclosed delimiter {delimiter!r}; expected {opening[delimiter]!r}.", *_position_of(source, position)
        ))
    return diagnostics


def _report_cpp_evaluator_gaps(source: str, diagnostics: list[Diagnostic]) -> None:
    features = {
        r"\b(?:std::|using\s+namespace)\b": "the C++ standard library and namespace directives are not executed",
        r"\b(?:map|unordered_map|string)\s*<": "C++ templates and containers other than the evaluator's vector facade are not executed",
    }
    _append_feature_diagnostics(source, diagnostics, "CPP_EVALUATOR_GAP", features)


def _report_java_evaluator_gaps(source: str, diagnostics: list[Diagnostic]) -> None:
    # System.out.print/println are implemented as evaluator output aliases.
    return


def _append_feature_diagnostics(
    source: str,
    diagnostics: list[Diagnostic],
    code: str,
    features: dict[str, str],
) -> None:
    for pattern, message in features.items():
        match = re.search(pattern, source)
        if match is not None:
            diagnostics.append(Diagnostic("unsupported", code, message, *_position_of(source, match.start())))


def _first_meaningful_line(source: str) -> tuple[int, str]:
    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith("//"):
            return line_number, line
    return 1, ""


def _line_of(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


def _position_of(source: str, index: int) -> tuple[int, int]:
    line = source.count("\n", 0, index) + 1
    previous_newline = source.rfind("\n", 0, index)
    return line, index - previous_newline
