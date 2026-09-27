"""Optional project configuration for the Polyglot command-line tool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    language: str | None = None
    engine: str | None = None
    max_call_depth: int | None = None
    max_loop_iterations: int | None = None


def load_project_config(path: Path | None) -> ProjectConfig:
    """Read a small ``polyglot.toml`` file, or return empty defaults."""
    if path is None:
        return ProjectConfig()
    try:
        with path.open("rb") as config_file:
            raw = tomllib.load(config_file)
    except FileNotFoundError as error:
        raise ValueError(f"Configuration file not found: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Invalid configuration file {path}: {error}") from error
    values = raw.get("polyglot", raw)
    if not isinstance(values, dict):
        raise ValueError("Configuration must contain a [polyglot] table")
    allowed = {"language", "engine", "max_call_depth", "max_loop_iterations"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Unknown configuration setting(s): {', '.join(sorted(unknown))}")
    language = values.get("language")
    engine = values.get("engine")
    max_call_depth = values.get("max_call_depth")
    max_loop_iterations = values.get("max_loop_iterations")
    if language is not None and language not in {"cpp", "java", "python"}:
        raise ValueError("Configuration language must be cpp, java, or python")
    if engine is not None and engine not in {"evaluator", "bytecode", "native"}:
        raise ValueError("Configuration engine must be evaluator, bytecode, or native")
    for name, value in (("max_call_depth", max_call_depth), ("max_loop_iterations", max_loop_iterations)):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
            raise ValueError(f"Configuration {name} must be a positive integer")
    return ProjectConfig(language, engine, max_call_depth, max_loop_iterations)
