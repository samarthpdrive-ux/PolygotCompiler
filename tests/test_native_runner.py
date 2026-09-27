"""Tests for native-toolchain command selection without invoking real compilers."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

from runtime.native_runner import NativeToolchainError, _java_main_class, run_native


class NativeRunnerTests(unittest.TestCase):
    def test_java_package_name_is_used_for_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Main.java"
            source.write_text("package demo.app; public class Main {}", encoding="utf-8")
            self.assertEqual(_java_main_class(source), "demo.app.Main")

    def test_missing_cpp_compiler_has_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "program.cpp"
            source.write_text("int main() {}", encoding="utf-8")
            with patch("runtime.native_runner.shutil.which", return_value=None):
                with self.assertRaisesRegex(NativeToolchainError, "g\\+\\+"):
                    run_native("cpp", source)

    @patch("runtime.native_runner._run_process")
    @patch("runtime.native_runner.shutil.which")
    def test_python_uses_current_python_runtime(self, mock_which: object, mock_run: object) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "program.py"
            source.write_text("print('ok')", encoding="utf-8")
            mock_run.return_value.returncode = 0
            result = run_native("python", source)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(mock_run.call_args.kwargs["cwd"], source.parent)

    @patch("runtime.native_runner._run_process")
    @patch("runtime.native_runner.shutil.which", return_value="C:\\MinGW\\bin\\g++.exe")
    def test_cpp_compile_failure_preserves_compiler_diagnostics(self, mock_which: object, mock_run: object) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "broken.cpp"
            source.write_text("int main( {", encoding="utf-8")
            mock_run.return_value = CompletedProcess([], 1, stdout="", stderr="broken.cpp:1: error: expected ')'")
            result = run_native("cpp", source, compile_only=True)
            self.assertEqual(result.stage, "compilation")
            self.assertEqual(result.returncode, 1)
            self.assertIn("expected ')'", result.stderr)
            self.assertTrue(mock_run.call_args.kwargs["capture_output"])

    def test_python_compile_only_returns_a_readable_syntax_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "broken.py"
            source.write_text("if True\n    pass\n", encoding="utf-8")
            result = run_native("python", source, compile_only=True)
            self.assertEqual(result.stage, "compilation")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SyntaxError", result.stderr)


if __name__ == "__main__":
    unittest.main()
