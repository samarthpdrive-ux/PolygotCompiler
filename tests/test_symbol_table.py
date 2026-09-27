"""Phase 3 tests for variable scopes, functions, and return propagation."""

import unittest

from core.symbol_table import SymbolTable


class SymbolTableTests(unittest.TestCase):
    def test_local_shadowing_does_not_change_global_binding(self) -> None:
        symbols = SymbolTable()
        symbols.define("score", 10)

        with symbols.scope("if-block"):
            symbols.define("score", 20)
            self.assertEqual(symbols.lookup("score"), 20)

        self.assertEqual(symbols.lookup("score"), 10)

    def test_assignment_updates_nearest_visible_binding(self) -> None:
        symbols = SymbolTable()
        symbols.define("total", 5)

        with symbols.scope("while-block"):
            symbols.assign("total", 8)

        self.assertEqual(symbols.lookup("total"), 8)

    def test_local_variable_is_removed_when_scope_exits(self) -> None:
        symbols = SymbolTable()
        with symbols.scope("temporary"):
            symbols.define("private_value", 99)
            self.assertTrue(symbols.is_defined("private_value"))

        self.assertFalse(symbols.is_defined("private_value"))
        with self.assertRaises(NameError):
            symbols.lookup("private_value")

    def test_function_binds_parameters_and_propagates_return_value(self) -> None:
        symbols = SymbolTable()
        symbols.define("offset", 100)
        symbols.define_function("add", ("left", "right"), body="add body")

        def execute_add(body: object, table: SymbolTable) -> None:
            self.assertEqual(body, "add body")
            table.define("intermediate", table.lookup("left") + table.lookup("right"))
            table.return_from_function(table.lookup("intermediate"))

        self.assertEqual(symbols.call_function("add", (4, 8), execute_add), 12)
        self.assertEqual(symbols.lookup("offset"), 100)
        self.assertFalse(symbols.is_defined("left"))
        self.assertFalse(symbols.is_defined("intermediate"))
        self.assertEqual(symbols.scope_depth, 1)

    def test_function_argument_count_is_checked(self) -> None:
        symbols = SymbolTable()
        symbols.define_function("identity", ("value",), body=None)
        with self.assertRaisesRegex(TypeError, r"identity\(\) expects 1 argument\(s\), got 0"):
            symbols.call_function("identity", (), lambda body, table: None)


if __name__ == "__main__":
    unittest.main()
