"""Interactive shell for executing small statements in one evaluator session."""

from __future__ import annotations

from collections.abc import Callable

from runtime.evaluator import Evaluator


def run_repl(
    language: str,
    lexer: Callable[[str], list],
    parser: Callable[[list], object],
    *,
    reader: Callable[[str], str] = input,
    writer: Callable[[str], None] = print,
) -> int:
    """Run a one-line educational REPL; use ``:quit`` or ``:globals``."""
    evaluator = Evaluator(output=lambda *values: writer(" ".join(str(value) for value in values)))
    writer(f"Polyglot {language} REPL. Type :quit to leave or :globals to inspect values.")
    while True:
        try:
            line = reader("polyglot> ")
        except EOFError:
            writer("")
            return 0
        command = line.strip()
        if command in {":quit", ":exit"}:
            return 0
        if command == ":globals":
            for name, value in evaluator.globals().items():
                writer(f"{name} = {value!r}")
            continue
        if not command:
            continue
        try:
            evaluator.evaluate(parser(lexer(line + ("" if line.endswith("\n") else "\n"))))
        except (AttributeError, IndexError, NameError, OSError, SyntaxError, TypeError, ValueError, RuntimeError) as error:
            writer(f"Error: {error}")
