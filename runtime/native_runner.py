"""Run complete source files with their native language toolchains."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path


class NativeToolchainError(RuntimeError):
    """Raised when a required compiler or runtime is not installed."""


@dataclass(frozen=True, slots=True)
class NativeResult:
    """Result and diagnostics from native compilation or execution."""

    returncode: int
    stage: str
    stdout: str = ""
    stderr: str = ""


def run_native(
    language: str,
    source: Path,
    *,
    timeout: int = 30,
    compile_only: bool = False,
) -> NativeResult:
    """Compile (where needed) and execute one complete source file.

    Standard input, output, and error remain connected to the terminal. This
    makes programs using C++ ``cin``, Java ``Scanner``, or Python ``input()``
    work interactively just as they do outside this project.
    """
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")
    runners = {"cpp": _run_cpp, "java": _run_java, "python": _run_python}
    try:
        runner = runners[language]
    except KeyError as error:
        raise ValueError(f"Unsupported language {language!r}") from error
    return runner(source.resolve(), timeout, compile_only)


def _run_cpp(source: Path, timeout: int, compile_only: bool) -> NativeResult:
    compiler = _require_tool("g++")
    with tempfile.TemporaryDirectory(prefix="polyglot-cpp-") as temporary_directory:
        executable = Path(temporary_directory) / "program.exe"
        compilation = _run_process(
            [compiler, str(source), "-std=c++17", "-o", str(executable)],
            cwd=source.parent,
            timeout=timeout,
            capture_output=True,
        )
        if compilation.returncode != 0:
            return NativeResult(compilation.returncode, "compilation", compilation.stdout, compilation.stderr)
        if compile_only:
            return NativeResult(0, "compilation")
        execution = _run_process([str(executable)], cwd=source.parent, timeout=timeout)
        return NativeResult(execution.returncode, "execution")


def _run_java(source: Path, timeout: int, compile_only: bool) -> NativeResult:
    compiler = _require_tool("javac")
    runtime = _require_tool("java")
    with tempfile.TemporaryDirectory(prefix="polyglot-java-") as temporary_directory:
        output_directory = Path(temporary_directory)
        compilation = _run_process(
            [compiler, "-d", str(output_directory), str(source)],
            cwd=source.parent,
            timeout=timeout,
            capture_output=True,
        )
        if compilation.returncode != 0:
            return NativeResult(compilation.returncode, "compilation", compilation.stdout, compilation.stderr)
        if compile_only:
            return NativeResult(0, "compilation")
        execution = _run_process(
            [runtime, "-cp", str(output_directory), _java_main_class(source)],
            cwd=source.parent,
            timeout=timeout,
        )
        return NativeResult(execution.returncode, "execution")


def _run_python(source: Path, timeout: int, compile_only: bool) -> NativeResult:
    if compile_only:
        try:
            compile(source.read_text(encoding="utf-8"), str(source), "exec")
        except SyntaxError as error:
            return NativeResult(1, "compilation", stderr="".join(traceback.format_exception_only(error)))
        return NativeResult(0, "compilation")
    execution = _run_process([sys.executable, str(source)], cwd=source.parent, timeout=timeout)
    return NativeResult(execution.returncode, "execution")


def _require_tool(name: str) -> str:
    tool = shutil.which(name)
    if tool is None:
        raise NativeToolchainError(
            f"Required native tool {name!r} was not found on PATH. Install it and restart PowerShell."
        )
    return tool


def _run_process(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            timeout=timeout,
            check=False,
            capture_output=capture_output,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"Native command timed out after {timeout} seconds: {command[0]}") from error


def _java_main_class(source: Path) -> str:
    """Derive the Java launch class, including an optional package name."""
    code = source.read_text(encoding="utf-8")
    package = re.search(r"\bpackage\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;", code)
    return f"{package.group(1)}.{source.stem}" if package else source.stem
