"""Phase 5 integration tests for parsing and unified AST execution."""

import tempfile
import unittest
from pathlib import Path

from frontends.cpp_lexer import lex_cpp
from frontends.cpp_parser import parse_cpp
from frontends.java_lexer import lex_java
from frontends.java_parser import parse_java
from frontends.python_lexer import lex_python
from frontends.python_parser import parse_python
from runtime.evaluator import Evaluator


class EvaluatorTests(unittest.TestCase):
    def test_python_arithmetic_condition_and_loop(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_python(lex_python(
            "score = 10 + 5 * 2\n"
            "if score > 15:\n"
            "    score = score - 1\n"
            "while score < 21:\n"
            "    score = score + 1\n"
        )))
        self.assertEqual(evaluator.globals()["score"], 21)

    def test_cpp_function_scope_and_return(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_cpp(lex_cpp(
            "int add(int left, int right) { int temporary = left + right; return temporary; } "
            "int result = add(4, 8);"
        )))
        self.assertEqual(evaluator.globals()["result"], 12)
        self.assertNotIn("left", evaluator.globals())
        self.assertNotIn("temporary", evaluator.globals())

    def test_java_object_method_call_and_instance_state(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_java(lex_java(
            "class Counter { int value = 0; void increment(int amount) { "
            "this.value = this.value + amount; } } "
            "Counter first = new Counter(); Counter second = new Counter(); "
            "first.increment(3); result = first.value + second.value;"
        )))
        self.assertEqual(evaluator.globals()["result"], 3)
        self.assertEqual(evaluator.globals()["first"].get_attribute("value"), 3)
        self.assertEqual(evaluator.globals()["second"].get_attribute("value"), 0)

    def test_print_builtin_uses_configured_output(self) -> None:
        output: list[tuple[object, ...]] = []
        evaluator = Evaluator(output=lambda *values: output.append(values))
        evaluator.evaluate(parse_python(lex_python("value = 7\nprint(value)\n")))
        self.assertEqual(output, [(7,)])

    def test_cpp_stream_output_aliases_use_configured_output(self) -> None:
        output: list[tuple[object, ...]] = []
        evaluator = Evaluator(output=lambda *values: output.append(values))
        evaluator.evaluate(parse_cpp(lex_cpp(
            '#include <iostream>\nint main() { cout << "ready" << endl; return 0; }'
        )))
        evaluator.call_function("main")
        self.assertEqual(output, [("ready",)])

    def test_java_system_output_aliases_use_configured_output(self) -> None:
        output: list[tuple[object, ...]] = []
        evaluator = Evaluator(output=lambda *values: output.append(values))
        evaluator.evaluate(parse_java(lex_java(
            'public class Main { public static void main(String[] args) { System.out.println("ready"); } }'
        )))
        evaluator.call_java_main("Main")
        self.assertEqual(output, [("ready",)])

    def test_python_input_strings_and_numeric_conversion(self) -> None:
        answers = iter(["Ada", "21"])
        prompts: list[str] = []
        evaluator = Evaluator(input_reader=lambda prompt: (prompts.append(prompt), next(answers))[1])
        evaluator.evaluate(parse_python(lex_python(
            'name = input("Name: ")\n'
            'age = int(input("Age: "))\n'
            'message = "Hello, " + name\n'
            'next_age = age + 1\n'
        )))
        self.assertEqual(prompts, ["Name: ", "Age: "])
        self.assertEqual(evaluator.globals()["message"], "Hello, Ada")
        self.assertEqual(evaluator.globals()["next_age"], 22)

    def test_cpp_cin_converts_to_declared_type(self) -> None:
        evaluator = Evaluator(input_reader=lambda prompt: "41")
        evaluator.evaluate(parse_cpp(lex_cpp("int age; cin >> age; int next_age = age + 1;")))
        self.assertEqual(evaluator.globals()["age"], 41)
        self.assertEqual(evaluator.globals()["next_age"], 42)

    def test_java_scanner_reads_integer(self) -> None:
        evaluator = Evaluator(input_reader=lambda prompt: "9")
        evaluator.evaluate(parse_java(lex_java(
            "Scanner scanner = new Scanner(System.in); "
            "int age = scanner.nextInt(); int doubled = age * 2;"
        )))
        self.assertEqual(evaluator.globals()["age"], 9)
        self.assertEqual(evaluator.globals()["doubled"], 18)

    def test_for_loops_execute_in_each_language_track(self) -> None:
        cpp = Evaluator()
        cpp.evaluate(parse_cpp(lex_cpp(
            "int total = 0; for (int item = 1; item < 4; item = item + 1) { total = total + item; }"
        )))
        java = Evaluator()
        java.evaluate(parse_java(lex_java(
            "int total = 0; for (int item = 1; item < 4; item = item + 1) { total = total + item; }"
        )))
        python = Evaluator()
        python.evaluate(parse_python(lex_python(
            "total = 0\nfor item in range(1, 4):\n    total = total + item\n"
        )))
        self.assertEqual(cpp.globals()["total"], 6)
        self.assertEqual(java.globals()["total"], 6)
        self.assertEqual(python.globals()["total"], 6)

    def test_arrays_lists_and_indexed_assignments_work_in_each_track(self) -> None:
        cpp = Evaluator()
        cpp.evaluate(parse_cpp(lex_cpp(
            "int marks[3] = {70, 80, 90}; marks[1] = 85; int total = marks[0] + marks[1] + marks[2];"
        )))
        java = Evaluator()
        java.evaluate(parse_java(lex_java(
            "int[] marks = {70, 80, 90}; marks[1] = 85; int total = marks[0] + marks[1] + marks[2];"
        )))
        python = Evaluator()
        python.evaluate(parse_python(lex_python(
            "marks = [70, 80, 90]\nmarks[1] = 85\ntotal = marks[0] + marks[1] + marks[2]\n"
        )))
        self.assertEqual(cpp.globals()["total"], 245)
        self.assertEqual(java.globals()["total"], 245)
        self.assertEqual(python.globals()["total"], 245)

    def test_array_size_allocates_writable_slots(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_cpp(lex_cpp("int values[2]; values[0] = 5; values[1] = 7;")))
        self.assertEqual(evaluator.globals()["values"], [5, 7])

    def test_parameterized_constructors_initialize_java_and_cpp_objects(self) -> None:
        java = Evaluator()
        java.evaluate(parse_java(lex_java(
            "class Student { String name; int age; "
            "Student(String studentName, int studentAge) { "
            "this.name = studentName; this.age = studentAge; } } "
            "Student student = new Student(\"Ada\", 21); result = student.age + 1;"
        )))
        cpp = Evaluator()
        cpp.evaluate(parse_cpp(lex_cpp(
            "class Student { string name; int age; "
            "Student(string studentName, int studentAge) { "
            "this.name = studentName; this.age = studentAge; } }; "
            "Student student = new Student(\"Ada\", 21); result = student.age + 1;"
        )))
        self.assertEqual(java.globals()["student"].get_attribute("name"), "Ada")
        self.assertEqual(cpp.globals()["student"].get_attribute("age"), 21)
        self.assertEqual(java.globals()["result"], 22)
        self.assertEqual(cpp.globals()["result"], 22)

    def test_constructor_argument_count_is_checked(self) -> None:
        evaluator = Evaluator()
        with self.assertRaisesRegex(TypeError, r"Student\(\) expects 1 argument\(s\), got 0"):
            evaluator.evaluate(parse_java(lex_java(
                "class Student { Student(String name) { } } Student student = new Student();"
            )))

    def test_break_and_continue_control_each_language_loop(self) -> None:
        cpp_source = (
            "int total = 0; for (int number = 1; number < 10; number = number + 1) { "
            "if (number == 5) { continue; } if (number == 8) { break; } total = total + number; }"
        )
        python_source = (
            "total = 0\nfor number in range(1, 10):\n"
            "    if number == 5:\n        continue\n"
            "    if number == 8:\n        break\n"
            "    total = total + number\n"
        )
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, cpp_source),
            (lex_java, parse_java, cpp_source),
            (lex_python, parse_python, python_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual(evaluator.globals()["total"], 23)

    def test_compound_assignments_and_increment_operators(self) -> None:
        cpp_source = "int score = 10; score += 5; score *= 2; score--; for (int item = 0; item < 3; item++) { score += item; }"
        python_source = "score = 10\nscore += 5\nscore *= 2\nscore -= 1\nfor item in range(3):\n    score += item\n"
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, cpp_source),
            (lex_java, parse_java, cpp_source),
            (lex_python, parse_python, python_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual(evaluator.globals()["score"], 32)

    def test_nested_logical_conditions_work_in_each_language_track(self) -> None:
        brace_source = (
            "int age = 20; int marks = 72; bool registered = true; int result = 0; "
            "if ((age >= 18 && marks >= 50) && registered) { result = 1; } "
            "if (!(marks < 50) || age < 18) { result += 10; }"
        )
        python_source = (
            "age = 20\nmarks = 72\nregistered = True\nresult = 0\n"
            "if (age >= 18 and marks >= 50) and registered:\n    result = 1\n"
            "if not (marks < 50) or age < 18:\n    result += 10\n"
        )
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, brace_source),
            (lex_java, parse_java, brace_source.replace("bool", "boolean")),
            (lex_python, parse_python, python_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual(evaluator.globals()["result"], 11)

    def test_twenty_string_operations_work_in_each_language_track(self) -> None:
        brace_declaration = "string"
        brace_source = (
            'string text = "  Hello World Hello  "; '
            'length = text.length(); upper = text.toUpperCase(); lower = text.toLowerCase(); trim = text.trim(); '
            'contains = text.contains("World"); starts = text.startsWith("  Hello"); ends = text.endsWith("  "); '
            'replaced = text.replace("World", "Codex"); part = text.substring(2, 7); letter = text.charAt(2); '
            'first = text.indexOf("Hello"); last = text.lastIndexOf("Hello"); empty = "".isEmpty(); '
            'same = text.equals("  Hello World Hello  "); words = text.split(" "); word = words[2]; '
            'repeated = "ha".repeat(3); reversed = text.reverse(); capitalized = "hello world".capitalize(); '
            'titled = "hello world".title(); count = text.count("Hello");'
        )
        python_source = (
            'text = "  Hello World Hello  "\n'
            'length = len(text)\nupper = text.upper()\nlower = text.lower()\ntrim = text.strip()\n'
            'contains = "World" in text\nstarts = text.startswith("  Hello")\nends = text.endswith("  ")\n'
            'replaced = text.replace("World", "Codex")\npart = text.substring(2, 7)\nletter = text.charAt(2)\n'
            'first = text.find("Hello")\nlast = text.rfind("Hello")\nempty = "".isEmpty()\n'
            'same = text.equals("  Hello World Hello  ")\nwords = text.split(" ")\nword = words[2]\n'
            'repeated = "ha".repeat(3)\nreversed = text.reverse()\ncapitalized = "hello world".capitalize()\n'
            'titled = "hello world".title()\ncount = text.count("Hello")\n'
        )
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, brace_source),
            (lex_java, parse_java, brace_source.replace(brace_declaration, "String", 1)),
            (lex_python, parse_python, python_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            values = evaluator.globals()
            self.assertEqual(values["length"], 21)
            self.assertEqual(values["upper"], "  HELLO WORLD HELLO  ")
            self.assertEqual(values["trim"], "Hello World Hello")
            self.assertTrue(values["contains"] and values["starts"] and values["ends"] and values["empty"] and values["same"])
            self.assertEqual(values["replaced"], "  Hello Codex Hello  ")
            self.assertEqual((values["part"], values["letter"], values["first"], values["last"]), ("Hello", "H", 2, 14))
            self.assertEqual((values["word"], values["repeated"], values["count"]), ("Hello", "hahaha", 2))
            self.assertEqual((values["capitalized"], values["titled"]), ("Hello world", "Hello World"))

    def test_ten_list_operations_work_in_each_language_track(self) -> None:
        brace_source = (
            "int marks[3] = {82, 70, 91}; marks.add(95); marks.remove(70); "
            "size = marks.size(); contains = marks.contains(91); index = marks.indexOf(91); "
            "marks.sort(); first = marks.get(0); previous = marks.set(0, 75); marks.reverse(); popped = marks.pop(); "
            "marks.clear(); length = marks.length();"
        )
        python_source = (
            "marks = [82, 70, 91]\nmarks.append(95)\nmarks.remove(70)\n"
            "size = len(marks)\ncontains = marks.contains(91)\nindex = marks.index(91)\n"
            "marks.sort()\nfirst = marks.get(0)\nprevious = marks.set(0, 75)\nmarks.reverse()\npopped = marks.pop()\n"
            "marks.clear()\nlength = marks.length()\n"
        )
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, brace_source),
            (lex_java, parse_java, brace_source),
            (lex_python, parse_python, python_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            values = evaluator.globals()
            self.assertEqual((values["size"], values["index"], values["first"], values["previous"], values["popped"], values["length"]), (3, 1, 82, 82, 75, 0))
            self.assertTrue(values["contains"])
            self.assertEqual(values["marks"], [])

    def test_else_if_and_elif_select_the_first_matching_branch(self) -> None:
        brace_source = (
            "int marks = 78; if (marks >= 90) { grade = \"A\"; } "
            "else if (marks >= 75) { grade = \"B\"; } "
            "else if (marks >= 50) { grade = \"C\"; } else { grade = \"D\"; }"
        )
        python_source = (
            "marks = 78\nif marks >= 90:\n    grade = \"A\"\nelif marks >= 75:\n    grade = \"B\"\n"
            "elif marks >= 50:\n    grade = \"C\"\nelse:\n    grade = \"D\"\n"
        )
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, brace_source),
            (lex_java, parse_java, brace_source),
            (lex_python, parse_python, python_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual(evaluator.globals()["grade"], "B")

    def test_switch_and_match_select_cases_and_brace_switch_falls_through(self) -> None:
        brace_source = (
            "int day = 2; int result = 0; switch (day) { "
            "case 1: result = 1; break; case 2: result = 2; case 3: result += 3; break; default: result = 9; }"
        )
        python_source = (
            "day = 2\nresult = 0\nmatch day:\n    case 1:\n        result = 1\n"
            "    case 2:\n        result = 2\n    case 3:\n        result = 3\n    case _:\n        result = 9\n"
        )
        for lexer, parser, source, expected in (
            (lex_cpp, parse_cpp, brace_source, 5),
            (lex_java, parse_java, brace_source, 5),
            (lex_python, parse_python, python_source, 2),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual(evaluator.globals()["result"], expected)

    def test_try_handlers_catch_runtime_errors_in_each_language_track(self) -> None:
        brace_source = (
            "int value = 0; try { value = 10 / 0; } catch { value = 42; }"
        )
        python_source = "value = 0\ntry:\n    value = 10 / 0\nexcept:\n    value = 42\n"
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, brace_source),
            (lex_java, parse_java, brace_source),
            (lex_python, parse_python, python_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual(evaluator.globals()["value"], 42)

    def test_sandboxed_file_operations_work_in_each_language_track(self) -> None:
        brace_source = (
            'before = fileExists("record.txt"); File file = open("record.txt", "w"); '
            'file.write("first\\nsecond"); file.flush(); file.close(); after = fileExists("record.txt"); '
            'File reader = open("record.txt", "r"); first = reader.readLine(); second = reader.read(); reader.close();'
        )
        python_source = (
            'before = fileExists("record.txt")\nfile = open("record.txt", "w")\nfile.write("first\\nsecond")\n'
            'file.flush()\nfile.close()\nafter = fileExists("record.txt")\nreader = open("record.txt", "r")\n'
            'first = reader.readLine()\nsecond = reader.read()\nreader.close()\n'
        )
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, brace_source),
            (lex_java, parse_java, brace_source),
            (lex_python, parse_python, python_source),
        ):
            with self.subTest(language=lexer.__name__), tempfile.TemporaryDirectory() as temporary_directory:
                sandbox = Path(temporary_directory)
                evaluator = Evaluator(sandbox_root=sandbox)
                evaluator.evaluate(parser(lexer(source)))
                values = evaluator.globals()
                self.assertFalse(values["before"])
                self.assertTrue(values["after"])
                self.assertEqual((values["first"], values["second"]), ("first", "second"))
                self.assertEqual((sandbox / "record.txt").read_text(encoding="utf-8"), "first\nsecond")

    def test_sandboxed_file_access_rejects_parent_path_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evaluator = Evaluator(sandbox_root=Path(temporary_directory))
            with self.assertRaisesRegex(PermissionError, "escapes the evaluator data folder"):
                evaluator.evaluate(parse_python(lex_python('file = open("../outside.txt", "w")\n')))

    def test_foreach_loops_and_do_while_work_in_supported_tracks(self) -> None:
        brace_source = (
            "int values[] = {1, 2, 3}; int total = 0; "
            "for (int value : values) { total += value; } "
            "do { total++; } while (total < 8);"
        )
        python_source = "values = [1, 2, 3]\ntotal = 0\nfor value in values:\n    total += value\n"
        for lexer, parser, source, expected in (
            (lex_cpp, parse_cpp, brace_source, 8),
            (lex_java, parse_java, brace_source, 8),
            (lex_python, parse_python, python_source, 6),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual(evaluator.globals()["total"], expected)

    def test_inheritance_provides_parent_attributes_and_allows_method_overrides(self) -> None:
        cpp_source = (
            "class Person { string name = \"Unknown\"; string label = \"\"; void describe() { label = name; } }; "
            "class Student : Person { void describe() { label = \"Student: \" + name; } }; "
            "Student student = new Student(); student.name = \"Ada\"; student.describe();"
        )
        java_source = cpp_source.replace("string", "String").replace("class Student : Person", "class Student extends Person").replace("}; Student", "} Student")
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, cpp_source),
            (lex_java, parse_java, java_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual(evaluator.globals()["student"].get_attribute("name"), "Ada")
            self.assertEqual(evaluator.globals()["student"].get_attribute("label"), "Student: Ada")

    def test_nested_array_literals_indexing_and_nested_foreach_loops(self) -> None:
        brace_source = (
            "int matrix[] = {{1, 2}, {3, 4}}; int total = 0; "
            "for (int row : matrix) { for (int value : row) { total += value; } } result = matrix[1][0];"
        )
        python_source = (
            "matrix = [[1, 2], [3, 4]]\ntotal = 0\nfor row in matrix:\n"
            "    for value in row:\n        total += value\nresult = matrix[1][0]\n"
        )
        for lexer, parser, source in (
            (lex_cpp, parse_cpp, brace_source),
            (lex_java, parse_java, brace_source),
            (lex_python, parse_python, python_source),
        ):
            evaluator = Evaluator()
            evaluator.evaluate(parser(lexer(source)))
            self.assertEqual((evaluator.globals()["total"], evaluator.globals()["result"]), (10, 3))

    def test_null_values_dictionaries_and_sets_work_in_python(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_python(lex_python(
            'missing = None\n'
            'scores = {"Ada": 90, "Lin": 82}\n'
            'scores["Lin"] = 85\n'
            'score = scores.get("Lin")\n'
            'names = scores.keys()\n'
            'unique = {1, 2, 2}\n'
            'unique.add(3)\n'
            'contains = unique.contains(2)\n'
            'count = len(unique)\n'
        )))
        values = evaluator.globals()
        self.assertIsNone(values["missing"])
        self.assertEqual((values["score"], values["names"], values["count"]), (85, ["Ada", "Lin"], 3))
        self.assertTrue(values["contains"])

    def test_dictionary_and_set_values_are_iterable_in_python_for_loops(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_python(lex_python(
            'scores = {"Ada": 2, "Lin": 3}\n'
            'total = 0\n'
            'for name in scores:\n'
            '    total += scores[name]\n'
            'unique = {1, 2}\n'
            'for value in unique:\n'
            '    total += value\n'
        )))
        self.assertEqual(evaluator.globals()["total"], 8)

    def test_java_and_cpp_collection_facades_support_generic_type_annotations(self) -> None:
        java = Evaluator()
        java.evaluate(parse_java(lex_java(
            'ArrayList<Integer> values = new ArrayList(); values.add(3); values.add(5); '
            'HashMap<String, Integer> scores = new HashMap(); scores.put("Ada", 8); total = values.size() + scores.get("Ada");'
        )))
        cpp = Evaluator()
        cpp.evaluate(parse_cpp(lex_cpp(
            'vector<int> values = new vector(); values.add(4); HashSet<int> unique = new HashSet(); '
            'unique.add(7); total = values.length() + unique.size();'
        )))
        self.assertEqual(java.globals()["total"], 10)
        self.assertEqual(cpp.globals()["total"], 2)

    def test_java_super_forwards_arguments_to_a_parent_constructor(self) -> None:
        evaluator = Evaluator()
        evaluator.evaluate(parse_java(lex_java(
            'class Person { String name; Person(String value) { this.name = value; } } '
            'class Student extends Person { int year; Student(String value, int level) { super(value); this.year = level; } } '
            'Student student = new Student("Ada", 3);'
        )))
        student = evaluator.globals()["student"]
        self.assertEqual((student.get_attribute("name"), student.get_attribute("year")), ("Ada", 3))


if __name__ == "__main__":
    unittest.main()
