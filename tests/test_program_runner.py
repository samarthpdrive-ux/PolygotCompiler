"""End-to-end tests for the checked-in valid/invalid program fixtures."""

from __future__ import annotations

import io
from pathlib import Path
import unittest

# Importing the public CLI establishes the same frontend import order used by
# subprocess cases, avoiding the package's intentionally eager runtime exports.
import main  # noqa: F401
from runtime.program_runner import load_program_cases, run_program_suite


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProgramRunnerTests(unittest.TestCase):
    def test_manifest_has_valid_and_invalid_cases_for_every_language(self) -> None:
        cases = load_program_cases(PROJECT_ROOT / "tests" / "programs")
        self.assertEqual({case.language for case in cases}, {"cpp", "java", "python"})
        self.assertTrue(any(case.expected_exit == 0 for case in cases))
        self.assertTrue(any(case.expected_exit != 0 for case in cases))
        self.assertTrue(all(case.path.is_file() for case in cases))

    def test_program_suite_passes(self) -> None:
        report = io.StringIO()
        result = run_program_suite(PROJECT_ROOT, output=report)
        self.assertTrue(result.success, report.getvalue())
        self.assertEqual(result.passed, 6)

    def test_program_suite_can_filter_a_language(self) -> None:
        report = io.StringIO()
        result = run_program_suite(PROJECT_ROOT, language="python", output=report)
        self.assertTrue(result.success, report.getvalue())
        self.assertEqual(result.passed, 2)


if __name__ == "__main__":
    unittest.main()
