"""Regression tests for type checking, tooling, IR, REPL, and new language subsets."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import main
from core.bytecode import BytecodeCompiler, BytecodeOptimizer, BytecodeVM, Instruction, disassemble
from core.linter import lint_program
from core.tooling import format_source
from core.type_checker import check_types
from frontends.cpp_lexer import lex_cpp
from frontends.cpp_parser import parse_cpp
from frontends.python_lexer import lex_python
from frontends.python_parser import parse_python
from frontends.java_lexer import lex_java
from frontends.java_parser import parse_java
from runtime.evaluator import Evaluator
from runtime.debugger import TraceDebugger
from runtime.repl import run_repl
from runtime.benchmark import benchmark_source, export_benchmark
from runtime.errors import CallDepthExceeded, format_runtime_error


class AdvancedFeatureTests(unittest.TestCase):
    def test_every_example_parses_with_its_frontend(self) -> None:
        project = Path(__file__).resolve().parents[1]
        pipelines = {
            '.py': (lex_python, parse_python),
            '.cpp': (lex_cpp, parse_cpp),
            '.java': (lex_java, parse_java),
        }
        for example in sorted((project / 'examples').glob('*.*')):
            if example.suffix not in pipelines:
                continue
            lexer, parser = pipelines[example.suffix]
            with self.subTest(example=example.name):
                parser(lexer(example.read_text(encoding='utf-8')))

    def test_static_type_checker_reports_definite_mismatches(self) -> None:
        diagnostics = check_types(parse_cpp(lex_cpp('int age = "wrong"; age = "still wrong";')))
        self.assertEqual(len(diagnostics), 2)
        self.assertIn("expected int, got string", diagnostics[0].message)

    def test_type_checker_checks_typed_function_returns(self) -> None:
        diagnostics = check_types(parse_cpp(lex_cpp('int answer() { return "wrong"; }')))
        self.assertTrue(any("return value" in item.message for item in diagnostics))

    def test_const_assignment_is_rejected(self) -> None:
        evaluator = Evaluator()
        with self.assertRaisesRegex(TypeError, "const variable"):
            evaluator.evaluate(parse_cpp(lex_cpp('const int limit = 3; limit = 4;')))

    def test_map_items_update_and_pop_operations(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_python(lex_python(
            'values = {"a": 1}\nvalues.update({"b": 2})\nitems = values.items()\n'
            'removed = values.pop("a")\n'
        )))
        self.assertEqual(evaluator.globals()["items"], [("a", 1), ("b", 2)])
        self.assertEqual(evaluator.globals()["removed"], 1)

    def test_linter_reports_duplicate_and_unreachable_statements(self) -> None:
        messages = lint_program(parse_python(lex_python('def run():\n    return 1\n    value = 2\n')))
        self.assertTrue(any("unreachable" in message for message in messages))

    def test_cpp_parent_initializer_forwards_constructor_arguments(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_cpp(lex_cpp(
            'class Person { string name; Person(string value) { this.name = value; } }; '
            'class Student : Person { Student(string value) : Person(value) { } }; '
            'Student student = new Student("Ada");'
        )))
        self.assertEqual(evaluator.globals()["student"].get_attribute("name"), "Ada")

    def test_python_tuple_literal_can_be_indexed_and_iterated(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_python(lex_python(
            'values = (2, 3, 4)\ntotal = values[0]\nfor value in values:\n    total += value\n'
        )))
        self.assertEqual(evaluator.globals()["total"], 11)

    def test_python_comprehension_safe_math_import_and_with_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evaluator = Evaluator(sandbox_root=Path(directory))
            evaluator.evaluate(parse_python(lex_python(
                'import math\n'
                'values = [value * 2 for value in [1, 2, 3]]\n'
                'root = math.sqrt(81)\n'
                'with open("result.txt", "w") as file:\n'
                '    file.write("saved")\n'
            )))
            self.assertEqual((evaluator.globals()["values"], evaluator.globals()["root"]), ([2, 4, 6], 9.0))
            self.assertEqual((Path(directory) / 'result.txt').read_text(encoding='utf-8'), 'saved')

    def test_trace_reports_execution_and_assignments(self) -> None:
        events: list[str] = []
        evaluator = Evaluator(trace=events.append)
        evaluator.evaluate(parse_python(lex_python('value = 1\nvalue += 2\n')))
        self.assertTrue(any("Assignment" in event for event in events))
        self.assertIn("value = 3", events)

    def test_debugger_can_break_on_a_source_line(self) -> None:
        events: list[str] = []
        debugger = TraceDebugger(line_breakpoints={2}, output=events.append)
        Evaluator(trace=debugger).evaluate(parse_python(lex_python('value = 1\nvalue += 2\n')))
        self.assertTrue(any('BREAK' in event and 'line 2' in event for event in events))

    def test_bytecode_vm_runs_straight_line_programs(self) -> None:
        program = parse_python(lex_python('value = 2 + 3\nprint(value)\n'))
        output: list[tuple[object, ...]] = []
        values = BytecodeVM(output=lambda *items: output.append(items)).run(BytecodeCompiler().compile(program))
        self.assertEqual(values["value"], 5)
        self.assertEqual(output, [(5,)])

    def test_bytecode_vm_runs_if_and_while_control_flow(self) -> None:
        program = parse_python(lex_python(
            'value = 0\nwhile value < 3:\n    value += 1\nif value == 3:\n    print(value)\n'
        ))
        output: list[tuple[object, ...]] = []
        values = BytecodeVM(output=lambda *items: output.append(items)).run(BytecodeCompiler().compile(program))
        self.assertEqual(values['value'], 3)
        self.assertEqual(output, [(3,)])

    def test_bytecode_vm_runs_counted_for_loop(self) -> None:
        program = parse_python(lex_python('total = 0\nfor item in range(3):\n    total += item\n'))
        values = BytecodeVM().run(BytecodeCompiler().compile(program))
        self.assertEqual(values['total'], 3)

    def test_bytecode_vm_runs_function_calls_and_returns(self) -> None:
        program = parse_python(lex_python(
            'def double(value):\n    return value * 2\nresult = double(6)\nprint(result)\n'
        ))
        output: list[tuple[object, ...]] = []
        values = BytecodeVM(output=lambda *items: output.append(items)).run(BytecodeCompiler().compile_module(program))
        self.assertEqual(values['result'], 12)
        self.assertEqual(output, [(12,)])

    def test_bytecode_vm_runs_classes_constructors_and_methods(self) -> None:
        program = parse_cpp(lex_cpp(
            'class Student { string name; int age; '
            'Student(string value, int years) { this.name = value; this.age = years; } '
            'int score() { return age + 1; } } '
            'Student student = new Student("Ada", 24); result = student.score();'
        ))
        values = BytecodeVM().run(BytecodeCompiler().compile_module(program))
        self.assertEqual(values['result'], 25)
        self.assertEqual(values['student'].state, {'name': 'Ada', 'age': 24})

    def test_bytecode_vm_runs_inheritance_and_overrides(self) -> None:
        program = parse_cpp(lex_cpp(
            'class Person { string name; Person(string value) { this.name = value; } '
            'void describe() { print(name); } } '
            'class Student : Person { Student(string value) : Person(value) { } '
            'void describe() { print("Student: " + name); } } '
            'Student student = new Student("Ada"); student.describe();'
        ))
        output: list[tuple[object, ...]] = []
        BytecodeVM(output=lambda *items: output.append(items)).run(BytecodeCompiler().compile_module(program))
        self.assertEqual(output, [('Student: Ada',)])

    def test_bytecode_vm_runs_static_fields_and_methods(self) -> None:
        program = parse_java(lex_java(
            'class Counter { static int total = 0; '
            'static void add(int value) { Counter.total += value; } } '
            'Counter.add(4); Counter.add(3); result = Counter.total;'
        ))
        values = BytecodeVM().run(BytecodeCompiler().compile_module(program))
        self.assertEqual(values['result'], 7)

    def test_bytecode_optimizer_folds_constants_and_preserves_results(self) -> None:
        program = parse_python(lex_python('value = (2 + 3) * 4\nprint(value)\n'))
        raw = BytecodeCompiler().compile_module(program)
        optimized = BytecodeOptimizer().optimize(raw)
        raw_output: list[tuple[object, ...]] = []
        optimized_output: list[tuple[object, ...]] = []
        raw_values = BytecodeVM(output=lambda *items: raw_output.append(items)).run(raw)
        optimized_values = BytecodeVM(output=lambda *items: optimized_output.append(items)).run(optimized)
        self.assertEqual((optimized_values, optimized_output), (raw_values, raw_output))
        self.assertLess(len(optimized.main), len(raw.main))
        self.assertIn(Instruction("PUSH", 20), optimized.main)

    def test_bytecode_optimizer_relocates_loop_jumps_and_removes_unreachable_code(self) -> None:
        program = parse_python(lex_python(
            'def answer():\n    return 2 + 3\n    hidden = 99\n'
            'total = 0\nwhile total < 2:\n    total += 1\nresult = answer()\n'
        ))
        optimized = BytecodeOptimizer().optimize(BytecodeCompiler().compile_module(program))
        values = BytecodeVM().run(optimized)
        self.assertEqual((values['total'], values['result']), (2, 5))
        self.assertNotIn('hidden', [item.operand for item in optimized.functions['answer'].instructions])

    def test_evaluator_enforces_recursive_call_depth(self) -> None:
        program = parse_python(lex_python('def loop():\n    return loop()\nvalue = loop()\n'))
        with self.assertRaisesRegex(RuntimeError, r'Maximum call depth \(4\) exceeded.*loop'):
            Evaluator(max_call_depth=4).evaluate(program)

    def test_bytecode_vm_enforces_recursive_call_depth(self) -> None:
        program = parse_python(lex_python('def loop():\n    return loop()\nvalue = loop()\n'))
        module = BytecodeCompiler().compile_module(program)
        with self.assertRaisesRegex(RuntimeError, r'Maximum call depth \(4\) exceeded.*loop'):
            BytecodeVM(max_call_depth=4).run(module)

    def test_recursive_instance_methods_work_in_evaluator_and_bytecode(self) -> None:
        program = parse_java(lex_java(
            'class Counter { int count(int value) { if (value <= 0) { return 0; } '
            'return 1 + count(value - 1); } } '
            'Counter counter = new Counter(); result = counter.count(5);'
        ))
        evaluator = Evaluator(max_call_depth=20)
        evaluator.evaluate(program)
        values = BytecodeVM(max_call_depth=20).run(BytecodeCompiler().compile_module(program))
        self.assertEqual((evaluator.globals()['result'], values['result']), (5, 5))

    def test_benchmark_compares_all_backends_and_exports_json(self) -> None:
        results = benchmark_source('python', 'result = (2 + 3) * 4\nprint(result)\n', 'bench.py')
        self.assertEqual([item.backend for item in results], ['evaluator', 'bytecode', 'bytecode-optimized'])
        self.assertEqual(results[0].output, ('20',))
        self.assertLess(results[-1].opcode_count, results[1].opcode_count)
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            export_benchmark(results, report)
            self.assertEqual(len(json.loads(report.read_text(encoding='utf-8'))), 3)
            csv_report = Path(directory) / 'report.csv'
            export_benchmark(results, csv_report)
            self.assertIn('backend,elapsed_ms,opcode_count,output,globals', csv_report.read_text(encoding='utf-8'))

    def test_call_depth_error_includes_code_and_call_chain(self) -> None:
        error = CallDepthExceeded(2, ['first()', 'second()', 'third()'])
        rendered = format_runtime_error(error)
        self.assertIn('[CALL_DEPTH]', rendered)
        self.assertIn('first() -> second() -> third()', rendered)

    def test_bytecode_disassembly_labels_module_sections(self) -> None:
        program = parse_python(lex_python('def answer():\n    return 5\nvalue = answer()\n'))
        rendered = disassemble(BytecodeCompiler().compile_module(program))
        self.assertIn('== main ==', rendered)
        self.assertIn('== function answer() ==', rendered)
        self.assertIn('CALL', rendered)

    def test_safe_formatter_normalizes_trailing_whitespace(self) -> None:
        self.assertEqual(format_source('value = 1  \r\n\r\n'), 'value = 1\n')

    def test_repl_preserves_a_single_evaluator_session(self) -> None:
        lines = iter(['value = 2', 'value += 3', ':globals', ':quit'])
        output: list[str] = []
        result = run_repl('python', lex_python, parse_python, reader=lambda prompt: next(lines), writer=output.append)
        self.assertEqual(result, 0)
        self.assertIn('value = 5', output)

    def test_cli_type_check_and_bytecode_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            typed = root / 'typed.py'
            typed.write_text('value = 2\n', encoding='utf-8')
            bytecode = root / 'bytecode.py'
            bytecode.write_text('value = 2 + 3\nprint(value)\n', encoding='utf-8')
            with patch.object(main.sys, 'argv', ['main.py', '--lang', 'python', '--type-check', str(typed)]):
                self.assertEqual(main.main(), 0)
            stdout = io.StringIO()
            with patch.object(main.sys, 'argv', ['main.py', '--lang', 'python', '--engine', 'bytecode', str(bytecode)]), redirect_stdout(stdout):
                self.assertEqual(main.main(), 0)
            self.assertIn('Bytecode execution completed.', stdout.getvalue())

    def test_cli_subcommands_route_through_the_same_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'program.py'
            source.write_text('value = 2 + 3\nprint(value)\n', encoding='utf-8')
            stdout = io.StringIO()
            with patch.object(main.sys, 'argv', ['main.py', 'compile', '--lang', 'python', str(source)]), redirect_stdout(stdout):
                self.assertEqual(main.main(), 0)
            self.assertIn('Bytecode execution completed.', stdout.getvalue())
            stdout = io.StringIO()
            with patch.object(main.sys, 'argv', ['main.py', 'format', '--lang', 'python', str(source)]), redirect_stdout(stdout):
                self.assertEqual(main.main(), 0)
            self.assertIn('value = 2 + 3', stdout.getvalue())

    def test_java_static_fields_and_methods_execute(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_java(lex_java(
            'class Counter { static int total = 0; static void add(int value) { Counter.total += value; } } '
            'Counter.add(4); Counter.add(3); result = Counter.total;'
        )))
        self.assertEqual(evaluator.globals()['result'], 7)

    def test_function_overloads_dispatch_by_argument_count(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_python(lex_python(
            'def score(value):\n    return value\n'
            'def score(left, right):\n    return left + right\n'
            'one = score(4)\ntwo = score(4, 5)\n'
        )))
        self.assertEqual((evaluator.globals()['one'], evaluator.globals()['two']), (4, 9))

    def test_java_method_overloads_dispatch_by_argument_count(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_java(lex_java(
            'class Calculator { int add(int value) { return value; } '
            'int add(int left, int right) { return left + right; } } '
            'Calculator calculator = new Calculator(); one = calculator.add(4); two = calculator.add(4, 5);'
        )))
        self.assertEqual((evaluator.globals()['one'], evaluator.globals()['two']), (4, 9))

    def test_cpp_reference_parameter_updates_caller_storage(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_cpp(lex_cpp(
            'void increment(int& value) { value += 1; } int count = 4; increment(count);'
        )))
        self.assertEqual(evaluator.globals()['count'], 5)

    def test_overload_selection_uses_parameter_type_when_available(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_java(lex_java(
            'class Formatter { String show(int value) { return "number"; } '
            'String show(String value) { return "text"; } } '
            'Formatter formatter = new Formatter(); result = formatter.show("ok");'
        )))
        self.assertEqual(evaluator.globals()['result'], 'text')


if __name__ == '__main__':
    unittest.main()
