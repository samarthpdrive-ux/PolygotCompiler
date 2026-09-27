"""Command-line entry point for the polyglot evaluator framework."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

from frontends.registry import FRONTENDS
from runtime.evaluator import Evaluator
from runtime.native_runner import NativeToolchainError, run_native
from core.validator import validate_source
from core.type_checker import check_types
from core.tooling import format_source
from core.bytecode import BytecodeCompiler, BytecodeOptimizer, BytecodeProfiler, BytecodeVM, disassemble
from core.linter import lint_program
from core.project_config import load_project_config
from runtime.repl import run_repl
from runtime.debugger import TraceDebugger
from runtime.program_runner import run_program_suite
from runtime.benchmark import benchmark_file, export_benchmark, format_benchmark
from runtime.errors import format_runtime_error


PIPELINES: dict[str, tuple[Callable[[str], list], Callable[[list], object]]] = {
    name: (frontend.lexer, frontend.parser) for name, frontend in FRONTENDS.items()
}

COMMANDS = {"run", "check", "compile", "debug", "format", "lint", "test", "benchmark"}


def normalize_command_line(argv: list[str]) -> list[str]:
    """Translate modern subcommands into the compatible flag-based CLI.

    Keeping this adapter means existing commands such as ``--lang python
    file.py`` continue to work while new users can use ``run``/``check`` and
    other focused commands without a second execution pipeline.
    """
    if not argv or argv[0] not in COMMANDS:
        return argv
    command, remainder = argv[0], list(argv[1:])
    implied = {
        "run": [],
        "check": ["--check"],
        "compile": ["--engine", "bytecode"],
        "debug": ["--trace"],
        "format": ["--format"],
        "lint": ["--lint"],
        "test": ["--test-all"],
        "benchmark": ["--benchmark"],
    }[command]
    if command == "compile" and "--engine" in remainder:
        implied = []
    return [*implied, *remainder]


def build_debugger(arguments: argparse.Namespace) -> TraceDebugger | None:
    """Create shared evaluator/bytecode debugger controls from CLI arguments."""
    if not (arguments.trace or arguments.step or arguments.breakpoints or arguments.line_breakpoints or arguments.watch):
        return None
    try:
        breakpoints = {int(value.strip()) for value in arguments.breakpoints.split(",") if value.strip()} if arguments.breakpoints else set()
        line_breakpoints = {int(value.strip()) for value in arguments.line_breakpoints.split(",") if value.strip()} if arguments.line_breakpoints else set()
    except ValueError as error:
        raise ValueError("Breakpoint values must be positive integers") from error
    if any(value <= 0 for value in breakpoints | line_breakpoints):
        raise ValueError("Breakpoint values must be positive integers")
    watches = {value.strip() for value in arguments.watch.split(",") if value.strip()} if arguments.watch else set()
    return TraceDebugger(
        breakpoints=breakpoints, line_breakpoints=line_breakpoints, watches=watches,
        step=arguments.step, trace_all=arguments.trace, output=print,
    )


def format_source_error(error: SyntaxError, source: str) -> str:
    """Render a lexer/parser error with the original source line and caret."""
    message = str(error)
    match = re.search(r"at line (\d+), column (\d+)", message)
    if match is None:
        hint = syntax_hint(message)
        rendered = f"Syntax error: {message}"
        return f"{rendered}\nHint: {hint}" if hint else rendered
    line_number, column = (int(value) for value in match.groups())
    lines = source.splitlines()
    source_line = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
    hint = syntax_hint(message)
    rendered = f"Syntax error: {message}\n{line_number:>4} | {source_line}\n     | {' ' * max(column - 1, 0)}^"
    return f"{rendered}\nHint: {hint}" if hint else rendered


def syntax_hint(message: str) -> str | None:
    """Return a short, actionable fix for a common parser diagnostic."""
    suggestions = (
        ("Expected ';'", "Add ';' at the end of this C++/Java statement."),
        ("Expected ':'", "Add ':' after the Python block header or dictionary key."),
        ("Expected '}'", "Close the current C++/Java block with '}'."),
        ("Expected ')'", "Close the parenthesized expression or argument list with ')'."),
        ("Expected ']'", "Close the array, list, or index expression with ']'."),
        ("Expected end of Python statement", "Check indentation or finish the Python statement."),
        (
            "Expected a number, string, variable, or parenthesized expression",
            "Add an expression after '=' or the operator, or remove the trailing operator.",
        ),
        ("Expected variable name", "Use an identifier such as total or item for the variable name."),
        ("Expected class name", "Provide a class identifier after the class declaration keyword."),
        ("Unexpected end of input", "Check for a missing closing brace, parenthesis, bracket, or statement terminator."),
    )
    return next((hint for prefix, hint in suggestions if prefix in message), None)


def format_parse_diagnostic(diagnostic: object, source: str) -> str:
    """Render a recovery-parser diagnostic with its original source caret."""
    message = getattr(diagnostic, "message", str(diagnostic))
    line_number = int(getattr(diagnostic, "line", 1))
    column = int(getattr(diagnostic, "column", 1))
    lines = source.splitlines()
    source_line = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
    hint = syntax_hint(message)
    rendered = (
        f"SYNTAX [PARSE] line {line_number}, column {column}: {message}\n"
        f"{line_number:>4} | {source_line}\n"
        f"     | {' ' * max(column - 1, 0)}^"
    )
    return f"{rendered}\nHint: {hint}" if hint else rendered


def main() -> int:
    """Read source code, run its language pipeline, and display global values."""
    argument_parser = argparse.ArgumentParser(description="Run a supported polyglot source subset.")
    argument_parser.add_argument("source", nargs="?", type=Path, help="Path to the source file to execute")
    argument_parser.add_argument("--lang", choices=PIPELINES, help="Source language")
    argument_parser.add_argument(
        "--engine",
        choices=("evaluator", "native", "bytecode"),
        default=None,
        help="Use the project's evaluator (default) or the language's native toolchain",
    )
    argument_parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Maximum seconds allowed for a native compile or execution command",
    )
    argument_parser.add_argument(
        "--compile-only",
        action="store_true",
        help="Compile/check native code without running it; requires --engine native",
    )
    argument_parser.add_argument("--tokens", action="store_true", help="Print the token stream before evaluation")
    argument_parser.add_argument("--ast", action="store_true", help="Print the AST before evaluation")
    argument_parser.add_argument("--trace", action="store_true", help="Print evaluator execution and assignment trace events")
    argument_parser.add_argument("--step", action="store_true", help="Print every evaluator trace event")
    argument_parser.add_argument("--break", dest="breakpoints", help="Comma-separated evaluator event numbers for breakpoints")
    argument_parser.add_argument("--break-line", dest="line_breakpoints", help="Comma-separated source lines for evaluator breakpoints")
    argument_parser.add_argument("--watch", help="Comma-separated variable names to watch in trace mode")
    argument_parser.add_argument("--profile", action="store_true", help="Report bytecode opcode counts and elapsed time")
    argument_parser.add_argument("--optimize", action="store_true", help="Optimize bytecode before execution or disassembly")
    argument_parser.add_argument("--disassemble", action="store_true", help="Print readable bytecode before execution")
    argument_parser.add_argument("--max-call-depth", type=int, help="Maximum nested function/method calls (default: 200)")
    argument_parser.add_argument("--max-loop-iterations", type=int, help="Maximum iterations per loop (default: 100000)")
    argument_parser.add_argument("--config", type=Path, help="Optional polyglot.toml project configuration file")
    argument_parser.add_argument("--type-check", action="store_true", help="Report static type errors without executing")
    argument_parser.add_argument("--strict-types", action="store_true", help="Reject type errors before evaluator execution")
    argument_parser.add_argument("--lint", action="store_true", help="Run structure, compatibility, and type diagnostics")
    argument_parser.add_argument("--format", action="store_true", help="Print safe whitespace-formatted source without executing")
    argument_parser.add_argument("--syntax-report", action="store_true", help="Collect recoverable parser errors without executing")
    argument_parser.add_argument("--repl", action="store_true", help="Start an interactive evaluator session; no source path is needed")
    argument_parser.add_argument(
        "--test-all", action="store_true",
        help="Run all checked-in valid/invalid program fixtures; optionally filter with --lang",
    )
    argument_parser.add_argument("--benchmark", action="store_true", help="Compare evaluator, bytecode, and optimized bytecode execution")
    argument_parser.add_argument("--benchmark-export", type=Path, help="Write benchmark results to .json or .csv")
    argument_parser.add_argument(
        "--check",
        action="store_true",
        help="Validate complete source-file structure and report evaluator compatibility without executing it",
    )
    arguments = argument_parser.parse_args(normalize_command_line(sys.argv[1:]))

    config_path = arguments.config
    if config_path is None:
        default_config = Path("polyglot.toml")
        config_path = default_config if default_config.is_file() else None
    try:
        config = load_project_config(config_path)
    except ValueError as error:
        argument_parser.error(str(error))
    arguments.lang = arguments.lang or config.language
    arguments.engine = arguments.engine or config.engine or "evaluator"
    arguments.max_call_depth = arguments.max_call_depth if arguments.max_call_depth is not None else (config.max_call_depth or 200)
    arguments.max_loop_iterations = arguments.max_loop_iterations if arguments.max_loop_iterations is not None else (config.max_loop_iterations or 100_000)

    if arguments.max_call_depth <= 0:
        argument_parser.error("--max-call-depth must be positive")
    if arguments.max_loop_iterations <= 0:
        argument_parser.error("--max-loop-iterations must be positive")

    if arguments.test_all:
        if arguments.source is not None:
            argument_parser.error("--test-all does not accept a source file")
        result = run_program_suite(Path(__file__).resolve().parent, language=arguments.lang)
        return 0 if result.success else 1

    if arguments.lang is None:
        argument_parser.error("--lang is required unless --test-all is used")

    if arguments.repl:
        if arguments.source is not None:
            argument_parser.error("--repl does not accept a source file")
        if arguments.engine != "evaluator":
            argument_parser.error("--repl requires --engine evaluator")
        lexer, parser = PIPELINES[arguments.lang]
        return run_repl(arguments.lang, lexer, parser)
    if arguments.source is None:
        argument_parser.error("source is required unless --repl is used")

    if arguments.benchmark:
        try:
            results = benchmark_file(
                arguments.lang, arguments.source, max_call_depth=arguments.max_call_depth,
                max_loop_iterations=arguments.max_loop_iterations,
            )
            print(format_benchmark(results))
            if arguments.benchmark_export is not None:
                export_benchmark(results, arguments.benchmark_export)
                print(f"Benchmark report written to {arguments.benchmark_export}")
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            print(format_runtime_error(error), file=sys.stderr)
            return 1
        return 0

    code: str | None = None
    if arguments.check or arguments.engine in {"evaluator", "bytecode"} or arguments.lint or arguments.format or arguments.type_check or arguments.syntax_report:
        try:
            code = arguments.source.read_text(encoding="utf-8")
        except FileNotFoundError:
            argument_parser.exit(2, f"Source file not found: {arguments.source}\n")
        except (OSError, UnicodeDecodeError) as error:
            argument_parser.exit(2, f"Could not read source file {arguments.source}: {error}\n")

    if arguments.check:
        validation = validate_source(arguments.lang, code, arguments.source.name)
        print(validation.format_report())
        return 0 if validation.structurally_valid else 1

    if arguments.syntax_report:
        try:
            frontend = FRONTENDS[arguments.lang]
            _, diagnostics = frontend.recovery_parser(frontend.lexer(code))
        except SyntaxError as error:
            print(format_source_error(error, code), file=sys.stderr)
            return 1
        if not diagnostics:
            print("Syntax report: no parser errors found.")
            return 0
        print(f"Syntax errors found: {len(diagnostics)}", file=sys.stderr)
        for diagnostic in diagnostics:
            print(format_parse_diagnostic(diagnostic, code), file=sys.stderr)
        return 1

    if arguments.format:
        print(format_source(code), end="")
        return 0

    if arguments.engine == "native":
        if arguments.timeout <= 0:
            argument_parser.error("--timeout must be positive")
        try:
            result = run_native(
                arguments.lang,
                arguments.source,
                timeout=arguments.timeout,
                compile_only=arguments.compile_only,
            )
        except (FileNotFoundError, NativeToolchainError, TimeoutError) as error:
            argument_parser.exit(2, f"Native execution failed: {error}\n")
        if result.returncode != 0:
            print(f"{arguments.lang.upper()} {result.stage} failed (exit code {result.returncode}).", file=sys.stderr)
            if result.stdout:
                print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", file=sys.stderr)
            if result.stderr:
                print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
        elif arguments.compile_only:
            print(f"{arguments.lang.upper()} compilation succeeded.")
        return result.returncode

    if arguments.compile_only:
        argument_parser.error("--compile-only requires --engine native")

    if arguments.lang in {"cpp", "java"}:
        validation = validate_source(arguments.lang, code, arguments.source.name)
        if not validation.structurally_valid:
            print(validation.format_report(), file=sys.stderr)
            return 1

    frontend = FRONTENDS[arguments.lang]
    lexer, parser = frontend.lexer, frontend.parser
    try:
        tokens = lexer(code)
        ast = parser(tokens)
    except SyntaxError as error:
        print(format_source_error(error, code), file=sys.stderr)
        return 1
    if arguments.tokens:
        for token in tokens:
            print(token)

    if arguments.ast:
        print(ast)

    type_diagnostics = check_types(ast)
    if arguments.type_check or arguments.lint:
        for diagnostic in type_diagnostics:
            print(f"TYPE [TYPE_MISMATCH]: {diagnostic.message}")
    if arguments.lint:
        for message in lint_program(ast):
            print(f"LINT: {message}")
        validation = validate_source(arguments.lang, code, arguments.source.name)
        print(validation.format_report())
        lint_messages = lint_program(ast)
        return 1 if type_diagnostics or lint_messages or not validation.structurally_valid else 0
    if arguments.type_check:
        return 1 if type_diagnostics else 0
    if arguments.strict_types and type_diagnostics:
        for diagnostic in type_diagnostics:
            print(f"Type error: {diagnostic.message}", file=sys.stderr)
        return 1

    try:
        debugger = build_debugger(arguments)
    except ValueError as error:
        argument_parser.error(str(error))

    if arguments.engine == "bytecode":
        try:
            instructions = BytecodeCompiler().compile_module(ast)
            if arguments.optimize:
                instructions = BytecodeOptimizer().optimize(instructions)
            if arguments.ast:
                for instruction in instructions.main:
                    print(instruction)
            if arguments.disassemble:
                print(disassemble(instructions))
            profiler = BytecodeProfiler() if arguments.profile else None
            vm = BytecodeVM(trace=debugger, profiler=profiler, max_call_depth=arguments.max_call_depth)
            values = vm.run(instructions)
            # Complete C++ files keep their int main() body as a function,
            # while Java files keep main(String[]) inside the public class.
            if arguments.lang == "cpp" and "main" in instructions.functions:
                vm.call_function("main", [])
            if arguments.lang == "java":
                entry_class = arguments.source.stem
                if entry_class in instructions.classes and "main" in instructions.classes[entry_class].static_methods:
                    parameters = instructions.classes[entry_class].static_methods["main"][0].parameters
                    vm.call_static(entry_class, "main", [[]] if len(parameters) == 1 else [])
            if profiler is not None:
                print(profiler.report())
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            print(format_runtime_error(error), file=sys.stderr)
            return 1
        print("Bytecode execution completed.")
        for name, value in values.items():
            print(f"{name} = {value!r}")
        return 0

    evaluator = Evaluator(
        trace=debugger if debugger is not None else None,
        max_call_depth=arguments.max_call_depth,
        max_loop_iterations=arguments.max_loop_iterations,
    )
    try:
        evaluator.evaluate(ast)
        # Complete C++ evaluator files may use the normal ``int main()`` wrapper.
        # Existing small subset examples can still contain top-level statements.
        if arguments.lang == "cpp" and evaluator.symbols.is_function_defined("main"):
            evaluator.call_function("main")
        if arguments.lang == "java":
            evaluator.call_java_main(arguments.source.stem)
    except (AttributeError, IndexError, NameError, OSError, TypeError, ValueError, RuntimeError) as error:
        print(format_runtime_error(error), file=sys.stderr)
        return 1
    print("Execution completed.")
    for name, value in evaluator.globals().items():
        print(f"{name} = {value!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
