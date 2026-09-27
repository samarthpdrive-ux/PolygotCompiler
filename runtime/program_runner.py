"""Integration runner for the checked-in example-program test suite.

The suite deliberately launches the public CLI in a subprocess.  This keeps
the tests close to how a student or examiner uses the compiler and prevents
implementation details from leaking into the fixture format.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from typing import Any, TextIO


@dataclass(frozen=True, slots=True)
class ProgramCase:
    """One valid or invalid source-program expectation."""

    name: str
    language: str
    path: Path
    expected_exit: int
    stdout_contains: tuple[str, ...] = ()
    stderr_contains: tuple[str, ...] = ()
    engine: str = "evaluator"


@dataclass(frozen=True, slots=True)
class ProgramSuiteResult:
    """Summary returned by :func:`run_program_suite`."""

    passed: int
    failed: int
    elapsed_seconds: float

    @property
    def success(self) -> bool:
        return self.failed == 0


def load_program_cases(suite_root: Path, language: str | None = None) -> list[ProgramCase]:
    """Load the JSON manifest and return cases, optionally for one language."""
    manifest_path = suite_root / "manifest.json"
    try:
        raw_cases: list[dict[str, Any]] = json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]
    except FileNotFoundError as error:
        raise ValueError(f"Program-suite manifest was not found: {manifest_path}") from error
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"Program-suite manifest is invalid: {manifest_path}: {error}") from error

    cases: list[ProgramCase] = []
    for raw in raw_cases:
        case = ProgramCase(
            name=str(raw["name"]),
            language=str(raw["language"]),
            path=suite_root / str(raw["path"]),
            expected_exit=int(raw["expected_exit"]),
            stdout_contains=tuple(str(item) for item in raw.get("stdout_contains", [])),
            stderr_contains=tuple(str(item) for item in raw.get("stderr_contains", [])),
            engine=str(raw.get("engine", "evaluator")),
        )
        if language is None or case.language == language:
            cases.append(case)
    if language is not None and not cases:
        raise ValueError(f"No program-suite cases are registered for language {language!r}")
    return cases


def run_program_suite(
    project_root: Path,
    *,
    language: str | None = None,
    output: TextIO = sys.stdout,
) -> ProgramSuiteResult:
    """Run valid and invalid fixtures through ``main.py`` and report results."""
    suite_root = project_root / "tests" / "programs"
    cases = load_program_cases(suite_root, language)
    started = perf_counter()
    passed = failed = 0
    for case in cases:
        command = [sys.executable, "main.py", "--lang", case.language]
        if case.engine != "evaluator":
            command.extend(("--engine", case.engine))
        command.append(str(case.path))
        completed = subprocess.run(command, cwd=project_root, capture_output=True, text=True, encoding="utf-8")
        problems = _verify_case(case, completed.returncode, completed.stdout, completed.stderr)
        if problems:
            failed += 1
            print(f"FAIL {case.name}: {'; '.join(problems)}", file=output)
        else:
            passed += 1
            print(f"PASS {case.name}", file=output)
    elapsed = perf_counter() - started
    print(f"Program suite: {passed} passed, {failed} failed ({elapsed:.3f}s)", file=output)
    return ProgramSuiteResult(passed, failed, elapsed)


def _verify_case(case: ProgramCase, returncode: int, stdout: str, stderr: str) -> list[str]:
    problems: list[str] = []
    if returncode != case.expected_exit:
        problems.append(f"expected exit {case.expected_exit}, got {returncode}")
    for text in case.stdout_contains:
        if text not in stdout:
            problems.append(f"stdout missing {text!r}")
    for text in case.stderr_contains:
        if text not in stderr:
            problems.append(f"stderr missing {text!r}")
    return problems
