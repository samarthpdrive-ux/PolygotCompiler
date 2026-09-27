"""Repeatable evaluator/bytecode benchmark runner for the teaching subset."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path
from time import perf_counter

from core.bytecode import BytecodeCompiler, BytecodeOptimizer, BytecodeProfiler, BytecodeVM
from frontends.registry import get_frontend
from runtime.evaluator import Evaluator


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    backend: str
    elapsed_ms: float
    opcode_count: int | None
    output: tuple[str, ...]
    globals: dict[str, str]


def benchmark_source(language: str, source: str, filename: str, *, max_call_depth: int = 200, max_loop_iterations: int = 100_000) -> list[BenchmarkResult]:
    """Run the same parsed source in evaluator, bytecode, and optimized bytecode."""
    frontend = get_frontend(language)
    _, program = frontend.parse(source)
    results = [
        _run_evaluator(language, filename, program, max_call_depth, max_loop_iterations),
        _run_bytecode(language, filename, program, False, max_call_depth),
        _run_bytecode(language, filename, program, True, max_call_depth),
    ]
    baseline = (results[0].output, results[0].globals)
    for item in results[1:]:
        if (item.output, item.globals) != baseline:
            raise RuntimeError(f"Benchmark correctness mismatch: {item.backend} differs from evaluator output/state")
    return results


def benchmark_file(language: str, path: Path, *, max_call_depth: int = 200, max_loop_iterations: int = 100_000) -> list[BenchmarkResult]:
    return benchmark_source(language, path.read_text(encoding="utf-8"), path.name, max_call_depth=max_call_depth, max_loop_iterations=max_loop_iterations)


def format_benchmark(results: list[BenchmarkResult]) -> str:
    lines = ["Backend              Time (ms)  Instructions", "-------------------  ---------  ------------"]
    for item in results:
        instructions = str(item.opcode_count) if item.opcode_count is not None else "-"
        lines.append(f"{item.backend:<19}  {item.elapsed_ms:>9.3f}  {instructions:>12}")
    return "\n".join(lines)


def export_benchmark(results: list[BenchmarkResult], path: Path) -> None:
    """Export a benchmark report as JSON or CSV based on its suffix."""
    payload = [asdict(item) for item in results]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return
    if path.suffix.lower() == ".csv":
        with path.open("w", newline="", encoding="utf-8") as report:
            writer = csv.DictWriter(report, fieldnames=("backend", "elapsed_ms", "opcode_count", "output", "globals"))
            writer.writeheader()
            for item in payload:
                writer.writerow({**item, "output": " | ".join(item["output"]), "globals": json.dumps(item["globals"], sort_keys=True)})
        return
    raise ValueError("Benchmark export path must end in .json or .csv")


def _run_evaluator(language: str, filename: str, program: object, max_call_depth: int, max_loop_iterations: int) -> BenchmarkResult:
    output: list[str] = []
    evaluator = Evaluator(output=lambda *values: output.append(" ".join(str(value) for value in values)), max_call_depth=max_call_depth, max_loop_iterations=max_loop_iterations)
    started = perf_counter()
    evaluator.evaluate(program)
    if language == "cpp" and evaluator.symbols.is_function_defined("main"):
        evaluator.call_function("main")
    if language == "java":
        evaluator.call_java_main(Path(filename).stem)
    elapsed = (perf_counter() - started) * 1000
    return BenchmarkResult("evaluator", elapsed, None, tuple(output), {name: repr(value) for name, value in evaluator.globals().items()})


def _run_bytecode(language: str, filename: str, program: object, optimized: bool, max_call_depth: int) -> BenchmarkResult:
    output: list[str] = []
    module = BytecodeCompiler().compile_module(program)
    if optimized:
        module = BytecodeOptimizer().optimize(module)
    profiler = BytecodeProfiler()
    vm = BytecodeVM(output=lambda *values: output.append(" ".join(str(value) for value in values)), profiler=profiler, max_call_depth=max_call_depth)
    started = perf_counter()
    values = vm.run(module)
    if language == "cpp" and "main" in module.functions:
        vm.call_function("main")
    if language == "java":
        class_name = Path(filename).stem
        if class_name in module.classes and "main" in module.classes[class_name].static_methods:
            parameters = module.classes[class_name].static_methods["main"][0].parameters
            vm.call_static(class_name, "main", [[]] if len(parameters) == 1 else [])
    elapsed = (perf_counter() - started) * 1000
    return BenchmarkResult("bytecode-optimized" if optimized else "bytecode", elapsed, sum(profiler.opcode_counts.values()), tuple(output), {name: repr(value) for name, value in values.items()})
