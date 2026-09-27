"""Packaging metadata tests for the installable ``polyglot`` command."""

from __future__ import annotations

import importlib
import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_pyproject_declares_standard_library_only_console_script(self) -> None:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as metadata_file:
            metadata = tomllib.load(metadata_file)

        self.assertEqual(metadata["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertEqual(metadata["project"]["dependencies"], [])
        self.assertEqual(metadata["project"]["scripts"]["polyglot"], "main:main")

    def test_console_entry_point_target_is_importable(self) -> None:
        entry_module, entry_function = "main:main".split(":", maxsplit=1)
        target = getattr(importlib.import_module(entry_module), entry_function)
        self.assertTrue(callable(target))
