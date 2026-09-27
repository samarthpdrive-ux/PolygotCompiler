"""Phase 4 tests for class parsing, object state, and method routing."""

import unittest

from core.ast_nodes import Assignment, CallExpression, ClassDeclaration, MemberAccess, ObjectDeclaration
from core.oop import ClassRegistry, MethodDefinition
from frontends.cpp_lexer import lex_cpp
from frontends.cpp_parser import parse_cpp
from frontends.java_lexer import lex_java
from frontends.java_parser import parse_java


class OopTests(unittest.TestCase):
    def test_java_class_parses_attributes_methods_and_object_construction(self) -> None:
        program = parse_java(lex_java(
            "class Counter { int value = 0; void increment(int amount) { "
            "this.value = this.value + amount; } } "
            "Counter counter = new Counter();"
        ))

        declaration, object_declaration = program.statements
        self.assertIsInstance(declaration, ClassDeclaration)
        self.assertEqual(declaration.name, "Counter")
        self.assertEqual([field.name for field in declaration.attributes], ["value"])
        self.assertEqual([method.name for method in declaration.methods], ["increment"])
        method_assignment = declaration.methods[0].body.statements[0]
        self.assertIsInstance(method_assignment, Assignment)
        self.assertIsInstance(method_assignment.target, MemberAccess)
        self.assertIsInstance(object_declaration, ObjectDeclaration)
        self.assertEqual(object_declaration.class_name, "Counter")

    def test_cpp_class_and_semicolon_are_parsed(self) -> None:
        program = parse_cpp(lex_cpp("class Counter { int value; void reset() { value = 0; } }; Counter item;"))
        self.assertIsInstance(program.statements[0], ClassDeclaration)
        self.assertIsInstance(program.statements[1], ObjectDeclaration)

    def test_instances_have_independent_state_and_bound_method_context(self) -> None:
        declaration = parse_java(lex_java(
            "class Counter { int value = 0; void increment(int amount) { value = value + amount; } }"
        )).statements[0]
        registry = ClassRegistry()
        registry.register_ast(declaration)
        first = registry.instantiate("Counter")
        second = registry.instantiate("Counter")

        def execute_increment(body: object, context: object) -> int:
            # The Phase 5 evaluator will interpret ``body``. This callback
            # verifies the Phase 4 binding and dispatch contract now.
            self.assertEqual(context.lookup("self"), context.instance)
            self.assertEqual(context.lookup("this"), context.instance)
            amount = context.lookup("amount")
            value = context.instance.get_attribute("value") + amount
            context.instance.set_attribute("value", value)
            return value

        self.assertEqual(registry.call_method(first, "increment", (3,), execute_increment), 3)
        self.assertEqual(first.get_attribute("value"), 3)
        self.assertEqual(second.get_attribute("value"), 0)

    def test_method_arity_is_checked(self) -> None:
        registry = ClassRegistry()
        registry.register("Point", methods={"move": MethodDefinition(("amount",), None)})
        point = registry.instantiate("Point")
        with self.assertRaisesRegex(TypeError, r"Point\.move\(\) expects 1 argument\(s\), got 0"):
            registry.call_method(point, "move", (), lambda body, context: None)

    def test_dot_notation_method_call_is_preserved_in_the_ast(self) -> None:
        assignment = parse_java(lex_java("result = counter.increment(3);")).statements[0]
        self.assertIsInstance(assignment, Assignment)
        self.assertIsInstance(assignment.value, CallExpression)
        self.assertIsInstance(assignment.value.callee, MemberAccess)
        self.assertEqual(assignment.value.callee.member, "increment")

    def test_java_constructor_is_preserved_in_class_ast(self) -> None:
        declaration = parse_java(lex_java(
            "class Student { String name; int age; "
            "Student(String studentName, int studentAge) { "
            "this.name = studentName; this.age = studentAge; } }"
        )).statements[0]
        self.assertIsInstance(declaration, ClassDeclaration)
        self.assertEqual(len(declaration.constructors), 1)
        self.assertEqual(declaration.constructors[0].parameters, ["studentName", "studentAge"])


if __name__ == "__main__":
    unittest.main()
