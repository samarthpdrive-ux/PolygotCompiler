"""Tests for optional project-level CLI defaults."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import main
from core.project_config import load_project_config


class ProjectConfigTests(unittest.TestCase):
    def test_loads_polyglot_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "polyglot.toml"
            path.write_text('[polyglot]\nlanguage = "python"\nengine = "bytecode"\nmax_call_depth = 12\n', encoding="utf-8")
            config = load_project_config(path)
        self.assertEqual((config.language, config.engine, config.max_call_depth), ("python", "bytecode", 12))

    def test_cli_config_defaults_yield_to_explicit_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "polyglot.toml"
            source = root / "program.py"
            config.write_text('[polyglot]\nlanguage = "python"\nengine = "bytecode"\n', encoding="utf-8")
            source.write_text('value = 2 + 3\nprint(value)\n', encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(main.sys, "argv", ["main.py", "--config", str(config), str(source)]), redirect_stdout(stdout):
                self.assertEqual(main.main(), 0)
            self.assertIn("Bytecode execution completed.", stdout.getvalue())
            stdout = io.StringIO()
            with patch.object(main.sys, "argv", ["main.py", "--config", str(config), "--engine", "evaluator", str(source)]), redirect_stdout(stdout):
                self.assertEqual(main.main(), 0)
            self.assertIn("Execution completed.", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
