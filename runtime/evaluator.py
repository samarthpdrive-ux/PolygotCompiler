"""Unified AST evaluator for the supported Phase 1–4 language subsets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
from pathlib import Path
from typing import IO
from typing import Any

from core.ast_nodes import (
    Assignment,
    ArrayDeclaration,
    BinaryOperation,
    Block,
    BooleanLiteral,
    BreakStatement,
    CallExpression,
    ClassDeclaration,
    ContinueStatement,
    DoWhileStatement,
    Expression,
    ExpressionStatement,
    ForStatement,
    ForEachStatement,
    FunctionDeclaration,
    Identifier,
    InputStatement,
    ImportStatement,
    IfStatement,
    IndexAccess,
    ListLiteral,
    ListComprehension,
    MappingLiteral,
    MemberAccess,
    NewExpression,
    NumberLiteral,
    NullLiteral,
    ObjectDeclaration,
    OutputStatement,
    Program,
    ReturnStatement,
    Statement,
    StringLiteral,
    SetLiteral,
    SuperConstructorCall,
    SwitchStatement,
    TryStatement,
    TupleLiteral,
    UnaryOperation,
    VariableDeclaration,
    WhileStatement,
    WithFileStatement,
)
from core.oop import ClassRegistry, MethodContext, MethodDefinition, ObjectInstance
from core.symbol_table import FunctionDefinition, ReturnSignal, SymbolTable
from runtime.errors import CallDepthExceeded


@dataclass(frozen=True, slots=True)
class InputScanner:
    """Marker object for the evaluator's lightweight Java ``Scanner`` support."""


@dataclass(slots=True)
class SandboxedFile:
    """One text stream whose resolved path is guaranteed to remain in ``data/``."""

    path: Path
    mode: str
    stream: IO[str]


@dataclass(frozen=True, slots=True)
class SafeMathModule:
    """Allow-listed operations exposed by evaluator-mode ``import math``."""


@dataclass(frozen=True, slots=True)
class ClassReference:
    """A class name used as the receiver of an evaluator static member call."""

    name: str


class BreakSignal(RuntimeError):
    """Internal control-flow signal used by ``break``."""


class ContinueSignal(RuntimeError):
    """Internal control-flow signal used by ``continue``."""


class Evaluator:
    """Execute a shared AST using one symbol table and class registry."""

    def __init__(
        self,
        *,
        output: Callable[..., None] = print,
        input_reader: Callable[[str], str] = input,
        trace: Callable[[str], None] | None = None,
        max_loop_iterations: int = 100_000,
        max_call_depth: int = 200,
        sandbox_root: Path | None = None,
    ) -> None:
        self.symbols = SymbolTable()
        self.classes = ClassRegistry()
        self.output = output
        self.input_reader = input_reader
        self.trace = trace
        self.max_loop_iterations = max_loop_iterations
        if max_call_depth <= 0:
            raise ValueError("max_call_depth must be positive")
        self.max_call_depth = max_call_depth
        self._call_depth = 0
        self._call_stack: list[str] = []
        self._variable_types: dict[str, str] = {}
        self._const_names: set[str] = set()
        self._active_instances: list[ObjectInstance] = []
        self._active_constructor_classes: list[str] = []
        self.sandbox_root = (sandbox_root or Path(__file__).resolve().parents[1] / "data").resolve()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def evaluate(self, node: Program | Statement | Expression) -> object | None:
        """Evaluate a program, statement, or expression AST node."""
        if self.trace is not None and isinstance(node, Statement):
            source_line = getattr(node, "source_line", None)
            location = f" at line {source_line}" if source_line is not None else ""
            self.trace(f"execute {type(node).__name__}{location}")
        if isinstance(node, Program):
            result: object | None = None
            try:
                for statement in node.statements:
                    result = self.evaluate(statement)
            except BreakSignal as error:
                raise RuntimeError("break used outside a loop") from error
            except ContinueSignal as error:
                raise RuntimeError("continue used outside a loop") from error
            return result
        if isinstance(node, Block):
            return self._evaluate_block(node)
        if isinstance(node, NumberLiteral | BooleanLiteral | StringLiteral):
            return node.value
        if isinstance(node, NullLiteral):
            return None
        if isinstance(node, ListLiteral):
            return [self.evaluate(element) for element in node.elements]
        if isinstance(node, ListComprehension):
            values = self.evaluate(node.iterable)
            if not isinstance(values, (list, tuple, str, dict, set)):
                raise TypeError("List comprehension requires an iterable value")
            result: list[object] = []
            with self.symbols.scope("list-comprehension"):
                for value in values:
                    self.symbols.define(node.name, value)
                    result.append(self.evaluate(node.element))
            return result
        if isinstance(node, MappingLiteral):
            return {self.evaluate(key): self.evaluate(value) for key, value in node.entries}
        if isinstance(node, SetLiteral):
            return {self.evaluate(element) for element in node.elements}
        if isinstance(node, TupleLiteral):
            return tuple(self.evaluate(element) for element in node.elements)
        if isinstance(node, Identifier):
            try:
                return self.symbols.lookup(node.name)
            except NameError:
                if self._active_instances and node.name in self._active_instances[-1].state:
                    return self._active_instances[-1].get_attribute(node.name)
                try:
                    self.classes.get_class(node.name)
                except NameError:
                    pass
                else:
                    return ClassReference(node.name)
                raise
        if isinstance(node, UnaryOperation):
            return self._evaluate_unary(node)
        if isinstance(node, BinaryOperation):
            return self._evaluate_binary(node)
        if isinstance(node, MemberAccess):
            instance = self.evaluate(node.object)
            if isinstance(instance, ClassReference):
                return self.classes.get_static_attribute(instance.name, node.member)
            if not isinstance(instance, ObjectInstance):
                raise TypeError(f"Cannot access {node.member!r} on a non-object value")
            return instance.get_attribute(node.member)
        if isinstance(node, IndexAccess):
            return self._get_indexed_value(node)
        if isinstance(node, NewExpression):
            return self._instantiate(node.class_name, [self.evaluate(argument) for argument in node.arguments])
        if isinstance(node, CallExpression):
            return self._evaluate_call(node)
        if isinstance(node, VariableDeclaration):
            value = self.evaluate(node.value) if node.value is not None else None
            self.symbols.define(node.name, value)
            self._variable_types[node.name] = node.declared_type
            if node.declared_type.startswith("const "):
                self._const_names.add(node.name)
            return value
        if isinstance(node, ArrayDeclaration):
            return self._evaluate_array_declaration(node)
        if isinstance(node, Assignment):
            value = self.evaluate(node.value)
            self._assign(node.target, value)
            return value
        if isinstance(node, ExpressionStatement):
            return self.evaluate(node.expression)
        if isinstance(node, InputStatement):
            value = self._convert_cpp_input(node.target, self._read_text(""))
            self._assign(node.target, value)
            return value
        if isinstance(node, OutputStatement):
            values = ["\n" if isinstance(value, Identifier) and value.name == "endl" else self.evaluate(value) for value in node.values]
            values = [value for value in values if value != "\n"]
            self.output(*values)
            return None
        if isinstance(node, SuperConstructorCall):
            if not self._active_instances or not self._active_constructor_classes:
                raise RuntimeError("super(...) may only be used inside a constructor")
            arguments = [self.evaluate(argument) for argument in node.arguments]
            return self.classes.call_parent_constructor(
                self._active_instances[-1], self._active_constructor_classes[-1], arguments, self._execute_method,
            )
        if isinstance(node, ImportStatement):
            if node.module != "math":
                raise PermissionError("Only the safe 'math' module may be imported in evaluator mode")
            self.symbols.define("math", SafeMathModule())
            return None
        if isinstance(node, WithFileStatement):
            resource = self.evaluate(node.resource)
            if not isinstance(resource, SandboxedFile):
                raise TypeError("with currently supports only open(...) sandboxed files")
            with self.symbols.scope("with-file"):
                self.symbols.define(node.name, resource)
                try:
                    return self._evaluate_block(node.body)
                finally:
                    if not resource.stream.closed:
                        resource.stream.close()
        if isinstance(node, IfStatement):
            if self._truthy(self.evaluate(node.condition)):
                return self._evaluate_block(node.then_branch)
            if node.else_branch is not None:
                return self._evaluate_block(node.else_branch)
            return None
        if isinstance(node, WhileStatement):
            return self._evaluate_while(node)
        if isinstance(node, ForStatement):
            return self._evaluate_for(node)
        if isinstance(node, ForEachStatement):
            return self._evaluate_foreach(node)
        if isinstance(node, DoWhileStatement):
            return self._evaluate_do_while(node)
        if isinstance(node, SwitchStatement):
            return self._evaluate_switch(node)
        if isinstance(node, TryStatement):
            return self._evaluate_try(node)
        if isinstance(node, BreakStatement):
            raise BreakSignal()
        if isinstance(node, ContinueStatement):
            raise ContinueSignal()
        if isinstance(node, FunctionDeclaration):
            self.symbols.define_function(node.name, node.parameters, node.body, node.parameter_types, node.parameter_by_reference)
            return None
        if isinstance(node, ReturnStatement):
            self.symbols.return_from_function(self.evaluate(node.value) if node.value is not None else None)
        if isinstance(node, ClassDeclaration):
            self._register_class(node)
            return None
        if isinstance(node, ObjectDeclaration):
            if node.class_name == "Scanner":
                # Supports: Scanner scanner = new Scanner(System.in);
                self.symbols.define(node.name, InputScanner())
                return self.symbols.lookup(node.name)
            if node.class_name in {"ArrayList", "Vector", "vector", "List"}:
                values = self._new_collection_list(node.constructor_arguments)
                self.symbols.define(node.name, values)
                return values
            if node.class_name in {"HashMap", "Map", "dict"}:
                values = self._new_collection_mapping(node.constructor_arguments)
                self.symbols.define(node.name, values)
                return values
            if node.class_name in {"HashSet", "Set", "set"}:
                values = self._new_collection_set(node.constructor_arguments)
                self.symbols.define(node.name, values)
                return values
            instance = self._instantiate(
                node.class_name,
                [self.evaluate(argument) for argument in node.constructor_arguments],
            )
            self.symbols.define(node.name, instance)
            return instance
        raise TypeError(f"Unsupported AST node: {type(node).__name__}")

    def globals(self) -> dict[str, object]:
        """Return a copy of global variables after execution."""
        return self.symbols.global_bindings()

    def call_function(self, name: str, arguments: list[object] | None = None) -> object | None:
        """Call a parsed global function, for example the C++ ``main`` entry point."""
        definition = self.symbols.get_function(name)
        return self.symbols.call_function(definition, arguments or [], self._execute_function)

    def call_java_main(self, class_name: str) -> object | None:
        """Run a normalized Java ``public static void main(String[] args)`` body."""
        instance = self.classes.instantiate(class_name)
        blueprint = self.classes.get_class(class_name)
        main_method = blueprint.static_methods.get("main") or blueprint.methods.get("main")
        if main_method is None:
            raise NameError(f"Java class {class_name!r} has no main method")
        arguments: list[object] = [[]] if len(main_method.parameters) == 1 else []
        if "main" in blueprint.static_methods:
            return self.classes.call_static_method(class_name, "main", arguments, self._execute_method)
        return self.classes.call_method(instance, "main", arguments, self._execute_method)

    def _evaluate_block(self, block: Block) -> object | None:
        result: object | None = None
        for statement in block.statements:
            result = self.evaluate(statement)
        return result

    def _evaluate_while(self, node: WhileStatement) -> object | None:
        result: object | None = None
        iterations = 0
        while self._truthy(self.evaluate(node.condition)):
            if iterations >= self.max_loop_iterations:
                raise RuntimeError(f"Loop exceeded {self.max_loop_iterations} iteration limit")
            try:
                result = self._evaluate_block(node.body)
            except ContinueSignal:
                pass
            except BreakSignal:
                break
            iterations += 1
        return result

    def _evaluate_for(self, node: ForStatement) -> object | None:
        """Execute a counted loop, applying its update after each body pass."""
        self.evaluate(node.initializer)
        result: object | None = None
        iterations = 0
        while self._truthy(self.evaluate(node.condition)):
            if iterations >= self.max_loop_iterations:
                raise RuntimeError(f"Loop exceeded {self.max_loop_iterations} iteration limit")
            try:
                result = self._evaluate_block(node.body)
            except ContinueSignal:
                pass
            except BreakSignal:
                break
            self.evaluate(node.update)
            iterations += 1
        return result

    def _evaluate_foreach(self, node: ForEachStatement) -> object | None:
        values = self.evaluate(node.iterable)
        if not isinstance(values, (list, tuple, str, dict, set)):
            raise TypeError("For-each loops require a list, tuple, array, string, dictionary, or set")
        result: object | None = None
        for index, value in enumerate(values):
            if index >= self.max_loop_iterations:
                raise RuntimeError(f"Loop exceeded {self.max_loop_iterations} iteration limit")
            if self.symbols.is_defined(node.name):
                self.symbols.assign(node.name, value)
            else:
                self.symbols.define(node.name, value)
            if node.declared_type is not None:
                self._variable_types[node.name] = node.declared_type
            try:
                result = self._evaluate_block(node.body)
            except ContinueSignal:
                continue
            except BreakSignal:
                break
        return result

    def _evaluate_do_while(self, node: DoWhileStatement) -> object | None:
        result: object | None = None
        iterations = 0
        while True:
            if iterations >= self.max_loop_iterations:
                raise RuntimeError(f"Loop exceeded {self.max_loop_iterations} iteration limit")
            try:
                result = self._evaluate_block(node.body)
            except ContinueSignal:
                pass
            except BreakSignal:
                break
            iterations += 1
            if not self._truthy(self.evaluate(node.condition)):
                break
        return result

    def _evaluate_switch(self, node: SwitchStatement) -> object | None:
        """Evaluate switch/match cases, honoring brace-language fall-through."""
        value = self.evaluate(node.expression)
        default_index: int | None = None
        selected_index: int | None = None
        for index, case in enumerate(node.cases):
            if case.value is None:
                default_index = index
            elif self.evaluate(case.value) == value:
                selected_index = index
                break
        if selected_index is None:
            selected_index = default_index
        if selected_index is None:
            return None

        result: object | None = None
        end = len(node.cases) if node.fall_through else selected_index + 1
        for case in node.cases[selected_index:end]:
            try:
                result = self._evaluate_block(case.body)
            except BreakSignal:
                break
        return result

    def _evaluate_try(self, node: TryStatement) -> object | None:
        """Execute a handler only for ordinary evaluator runtime failures."""
        try:
            return self._evaluate_block(node.try_branch)
        except (AttributeError, IndexError, KeyError, NameError, TypeError, ValueError, ZeroDivisionError):
            return self._evaluate_block(node.except_branch)

    def _assign(self, target: Expression, value: object) -> None:
        if isinstance(target, Identifier):
            if target.name in self._const_names:
                raise TypeError(f"Cannot assign to const variable {target.name!r}")
            if self.symbols.is_defined(target.name):
                self.symbols.assign(target.name, value)
            elif self._active_instances and target.name in self._active_instances[-1].state:
                self._active_instances[-1].set_attribute(target.name, value)
            else:
                self.symbols.define(target.name, value)
            if self.trace is not None:
                self.trace(f"{target.name} = {value!r}")
            return
        if isinstance(target, MemberAccess):
            instance = self.evaluate(target.object)
            if isinstance(instance, ClassReference):
                self.classes.set_static_attribute(instance.name, target.member, value)
                return
            if not isinstance(instance, ObjectInstance):
                raise TypeError(f"Cannot assign member {target.member!r} on a non-object value")
            instance.set_attribute(target.member, value)
            return
        if isinstance(target, IndexAccess):
            values = self.evaluate(target.object)
            index = self.evaluate(target.index)
            if isinstance(values, dict):
                values[index] = value
                return
            self._validate_index(values, index)
            values[index] = value
            return
        raise TypeError("Assignment target must be a variable, array element, or object attribute")

    def _evaluate_array_declaration(self, node: ArrayDeclaration) -> list[object | None]:
        values = [self.evaluate(value) for value in node.values] if node.values is not None else []
        if node.size is None:
            allocated: list[object | None] = values
        else:
            size = self.evaluate(node.size)
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ValueError("Array size must be a non-negative integer")
            if len(values) > size:
                raise ValueError(f"Array {node.name!r} has {len(values)} values but size {size}")
            allocated = values + [None] * (size - len(values))
        self.symbols.define(node.name, allocated)
        self._variable_types[node.name] = f"{node.declared_type}[]"
        return allocated

    def _get_indexed_value(self, node: IndexAccess) -> object:
        values = self.evaluate(node.object)
        index = self.evaluate(node.index)
        if isinstance(values, dict):
            return values[index]
        if isinstance(values, tuple):
            if not isinstance(index, int) or isinstance(index, bool):
                raise TypeError("Tuple index must be an integer")
            return values[index]
        self._validate_index(values, index)
        return values[index]

    @staticmethod
    def _validate_index(values: object, index: object) -> None:
        if not isinstance(values, list):
            raise TypeError("Only lists and arrays support numeric indexing")
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("Array index must be an integer")
        if not -len(values) <= index < len(values):
            raise IndexError(f"Array index {index} is out of range")

    def _evaluate_call(self, node: CallExpression) -> object | None:
        arguments = [self.evaluate(argument) for argument in node.arguments]
        if isinstance(node.callee, MemberAccess) and self._is_java_output_call(node.callee):
            if node.callee.member not in {"print", "println"}:
                raise AttributeError(f"Unsupported System.out method {node.callee.member!r}")
            self.output(*arguments)
            return None
        if isinstance(node.callee, Identifier):
            if node.callee.name == "print":
                self.output(*arguments)
                return None
            if node.callee.name == "input":
                if len(arguments) > 1:
                    raise TypeError("input() accepts at most one prompt argument")
                return self._read_text(str(arguments[0]) if arguments else "")
            if node.callee.name in {"int", "float", "str"}:
                if len(arguments) != 1:
                    raise TypeError(f"{node.callee.name}() expects exactly one argument")
                converters: Mapping[str, Callable[[object], object]] = {"int": int, "float": float, "str": str}
                try:
                    return converters[node.callee.name](arguments[0])
                except (TypeError, ValueError) as error:
                    raise ValueError(f"Cannot convert {arguments[0]!r} with {node.callee.name}()") from error
            if node.callee.name == "len":
                if len(arguments) != 1 or not isinstance(arguments[0], (str, list, tuple, dict, set)):
                    raise TypeError("len() expects one string, list, tuple, dictionary, or set argument")
                return len(arguments[0])
            if node.callee.name == "dict":
                if arguments:
                    raise TypeError("dict() accepts no arguments in this subset")
                return {}
            if node.callee.name == "set":
                if len(arguments) > 1:
                    raise TypeError("set() accepts zero or one iterable argument")
                return set(arguments[0]) if arguments else set()
            if node.callee.name == "open":
                return self._open_sandboxed_file(arguments)
            if node.callee.name == "fileExists":
                if len(arguments) != 1 or not isinstance(arguments[0], str):
                    raise TypeError("fileExists() expects one file-name string")
                return self._resolve_sandbox_path(arguments[0]).is_file()
            if node.callee.name in {"readInt", "readFloat", "readLine"}:
                if arguments:
                    raise TypeError(f"{node.callee.name}() does not accept arguments")
                converters: Mapping[str, Callable[[str], object]] = {
                    "readInt": int, "readFloat": float, "readLine": lambda value: value,
                }
                return self._convert_input(self._read_text(""), converters[node.callee.name], node.callee.name)
            # Java/C++ permit an instance method to call itself without
            # writing ``this.``. Route that form before global functions.
            if self._active_instances:
                instance = self._active_instances[-1]
                blueprint = self.classes.get_class(instance.class_name)
                if node.callee.name in blueprint.methods:
                    return self.classes.call_method(instance, node.callee.name, arguments, self._execute_method)
            raw_arguments: list[object] = []
            argument_types: list[str] = []
            for argument in node.arguments:
                if isinstance(argument, Identifier):
                    raw_arguments.append(argument.name)
                    argument_types.append(self._variable_types.get(argument.name, self._runtime_type(self.evaluate(argument))))
                else:
                    value = self.evaluate(argument)
                    raw_arguments.append(value)
                    argument_types.append(self._runtime_type(value))
            definition = self.symbols.get_function(node.callee.name, len(raw_arguments), argument_types)
            arguments = [
                item if index < len(definition.parameter_by_reference) and definition.parameter_by_reference[index]
                else (self.evaluate(node.arguments[index]) if isinstance(node.arguments[index], Identifier) else item)
                for index, item in enumerate(raw_arguments)
            ]
            return self.symbols.call_function(definition, arguments, self._execute_function)
        if isinstance(node.callee, MemberAccess):
            instance = self.evaluate(node.callee.object)
            if isinstance(instance, InputScanner):
                return self._evaluate_scanner_call(node.callee.member, arguments)
            if isinstance(instance, SafeMathModule):
                return self._evaluate_math_method(node.callee.member, arguments)
            if isinstance(instance, ClassReference):
                return self.classes.call_static_method(instance.name, node.callee.member, arguments, self._execute_method)
            if isinstance(instance, SandboxedFile):
                return self._evaluate_file_method(instance, node.callee.member, arguments)
            if isinstance(instance, str):
                return self._evaluate_string_method(instance, node.callee.member, arguments)
            if isinstance(instance, list):
                return self._evaluate_list_method(instance, node.callee.member, arguments)
            if isinstance(instance, dict):
                return self._evaluate_mapping_method(instance, node.callee.member, arguments)
            if isinstance(instance, set):
                return self._evaluate_set_method(instance, node.callee.member, arguments)
            if not isinstance(instance, ObjectInstance):
                raise TypeError(f"Cannot call {node.callee.member!r} on a non-object value")
            return self.classes.call_method(instance, node.callee.member, arguments, self._execute_method)
        raise TypeError("Only functions and object methods can be called")

    @staticmethod
    def _evaluate_math_method(method: str, arguments: list[object]) -> object:
        operations: Mapping[str, Callable[..., object]] = {
            "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
            "pow": pow, "abs": abs,
        }
        try:
            operation = operations[method]
        except KeyError as error:
            raise AttributeError(f"Unsupported math method {method!r}") from error
        try:
            return operation(*arguments)
        except TypeError as error:
            raise TypeError(f"Invalid arguments for math.{method}()") from error

    def _new_collection_list(self, arguments: list[Expression]) -> list[object]:
        if len(arguments) > 1:
            raise TypeError("Collection constructors accept zero or one iterable argument")
        return list(self.evaluate(arguments[0])) if arguments else []

    @staticmethod
    def _runtime_type(value: object) -> str:
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "string"
        return "unknown"

    def _new_collection_mapping(self, arguments: list[Expression]) -> dict[object, object]:
        if arguments:
            raise TypeError("Map constructors accept no arguments in this subset")
        return {}

    def _new_collection_set(self, arguments: list[Expression]) -> set[object]:
        if len(arguments) > 1:
            raise TypeError("Set constructors accept zero or one iterable argument")
        return set(self.evaluate(arguments[0])) if arguments else set()

    @staticmethod
    def _is_java_output_call(callee: MemberAccess) -> bool:
        """Recognize the safe subset of ``System.out.print/println``."""
        return (
            isinstance(callee.object, MemberAccess)
            and callee.object.member == "out"
            and isinstance(callee.object.object, Identifier)
            and callee.object.object.name == "System"
        )

    def _open_sandboxed_file(self, arguments: list[object]) -> SandboxedFile:
        """Open an UTF-8 text file inside the evaluator's project-local sandbox."""
        if len(arguments) not in {1, 2} or not isinstance(arguments[0], str):
            raise TypeError("open() expects a file-name string and optional mode")
        mode = arguments[1] if len(arguments) == 2 else "r"
        if not isinstance(mode, str) or mode not in {"r", "w", "a"}:
            raise ValueError("open() supports only text modes 'r', 'w', and 'a'")
        path = self._resolve_sandbox_path(arguments[0])
        stream = path.open(mode, encoding="utf-8")
        return SandboxedFile(path, mode, stream)

    def _resolve_sandbox_path(self, filename: str) -> Path:
        candidate_path = Path(filename)
        if candidate_path.is_absolute():
            raise PermissionError("Absolute paths are not allowed; use a name inside the data folder")
        candidate = (self.sandbox_root / candidate_path).resolve()
        if candidate != self.sandbox_root and self.sandbox_root not in candidate.parents:
            raise PermissionError("File path escapes the evaluator data folder")
        if candidate == self.sandbox_root:
            raise IsADirectoryError("A file name is required")
        return candidate

    @staticmethod
    def _evaluate_file_method(file: SandboxedFile, method: str, arguments: list[object]) -> object | None:
        """Execute safe text-file operations on an already sandboxed stream."""
        if method == "write":
            if len(arguments) != 1 or not isinstance(arguments[0], str):
                raise TypeError("File.write() expects one text string")
            return file.stream.write(arguments[0])
        if method == "read":
            if arguments:
                raise TypeError("File.read() expects no arguments")
            return file.stream.read()
        if method == "readLine":
            if arguments:
                raise TypeError("File.readLine() expects no arguments")
            return file.stream.readline().rstrip("\r\n")
        if method == "flush":
            if arguments:
                raise TypeError("File.flush() expects no arguments")
            file.stream.flush()
            return None
        if method == "close":
            if arguments:
                raise TypeError("File.close() expects no arguments")
            file.stream.close()
            return None
        raise AttributeError("Supported file methods are write(), read(), readLine(), flush(), and close()")

    @staticmethod
    def _evaluate_string_method(text: str, method: str, arguments: list[object]) -> object:
        """Run the evaluator's 20 documented Java/C++/Python string operations."""
        no_argument_methods: Mapping[str, Callable[[], object]] = {
            "length": lambda: len(text),
            "upper": text.upper,
            "toUpperCase": text.upper,
            "lower": text.lower,
            "toLowerCase": text.lower,
            "trim": text.strip,
            "strip": text.strip,
            "isEmpty": lambda: not text,
            "reverse": lambda: text[::-1],
            "capitalize": text.capitalize,
            "title": text.title,
        }
        if method in no_argument_methods:
            if arguments:
                raise TypeError(f"String.{method}() expects no arguments")
            return no_argument_methods[method]()

        def require_text(count: int) -> list[str]:
            if len(arguments) != count or not all(isinstance(argument, str) for argument in arguments):
                raise TypeError(f"String.{method}() expects {count} string argument(s)")
            return arguments  # type: ignore[return-value]

        if method in {"contains", "startsWith", "startswith", "endsWith", "endswith", "equals", "find", "indexOf", "rfind", "lastIndexOf", "count"}:
            value = require_text(1)[0]
            operations: Mapping[str, Callable[[str], object]] = {
                "contains": lambda item: item in text,
                "startsWith": text.startswith,
                "startswith": text.startswith,
                "endsWith": text.endswith,
                "endswith": text.endswith,
                "equals": lambda item: text == item,
                "find": text.find,
                "indexOf": text.find,
                "rfind": text.rfind,
                "lastIndexOf": text.rfind,
                "count": text.count,
            }
            return operations[method](value)
        if method == "replace":
            old, new = require_text(2)
            return text.replace(old, new)
        if method in {"substring", "charAt"}:
            expected = 1 if method == "charAt" else None
            if (expected is not None and len(arguments) != expected) or (method == "substring" and len(arguments) not in {1, 2}):
                raise TypeError(f"String.{method}() has an invalid number of arguments")
            if not all(isinstance(argument, int) and not isinstance(argument, bool) for argument in arguments):
                raise TypeError(f"String.{method}() expects integer index arguments")
            if method == "charAt":
                return text[arguments[0]]
            return text[arguments[0]:] if len(arguments) == 1 else text[arguments[0]:arguments[1]]
        if method == "split":
            if len(arguments) > 1 or (arguments and not isinstance(arguments[0], str)):
                raise TypeError("String.split() accepts zero or one string argument")
            return text.split(arguments[0] if arguments else None)
        if method == "repeat":
            if len(arguments) != 1 or not isinstance(arguments[0], int) or isinstance(arguments[0], bool):
                raise TypeError("String.repeat() expects one integer argument")
            if arguments[0] < 0:
                raise ValueError("String.repeat() count cannot be negative")
            return text * arguments[0]
        raise AttributeError(
            f"Unsupported string method {method!r}. See README for the 20 supported string operations."
        )

    @staticmethod
    def _evaluate_list_method(values: list[object], method: str, arguments: list[object]) -> object | None:
        """Run the evaluator's documented list/array methods and aliases."""
        if method in {"append", "add"}:
            if len(arguments) != 1:
                raise TypeError(f"List.{method}() expects one argument")
            values.append(arguments[0])
            return None
        if method == "remove":
            if len(arguments) != 1:
                raise TypeError("List.remove() expects one argument")
            try:
                values.remove(arguments[0])
            except ValueError as error:
                raise ValueError(f"List.remove() could not find {arguments[0]!r}") from error
            return None
        if method == "pop":
            if len(arguments) > 1:
                raise TypeError("List.pop() accepts zero or one index argument")
            if not arguments:
                return values.pop()
            index = Evaluator._list_index(arguments[0], method)
            return values.pop(index)
        if method == "clear":
            if arguments:
                raise TypeError("List.clear() expects no arguments")
            values.clear()
            return None
        if method in {"length", "size"}:
            if arguments:
                raise TypeError(f"List.{method}() expects no arguments")
            return len(values)
        if method == "contains":
            if len(arguments) != 1:
                raise TypeError("List.contains() expects one argument")
            return arguments[0] in values
        if method in {"indexOf", "index"}:
            if len(arguments) != 1:
                raise TypeError(f"List.{method}() expects one argument")
            try:
                return values.index(arguments[0])
            except ValueError:
                return -1
        if method == "reverse":
            if arguments:
                raise TypeError("List.reverse() expects no arguments")
            values.reverse()
            return None
        if method == "sort":
            if arguments:
                raise TypeError("List.sort() expects no arguments")
            try:
                values.sort()
            except TypeError as error:
                raise TypeError("List.sort() requires comparable values of compatible types") from error
            return None
        if method == "get":
            if len(arguments) != 1:
                raise TypeError("List.get() expects one index argument")
            return values[Evaluator._list_index(arguments[0], method)]
        if method == "set":
            if len(arguments) != 2:
                raise TypeError("List.set() expects an index and value")
            index = Evaluator._list_index(arguments[0], method)
            previous = values[index]
            values[index] = arguments[1]
            return previous
        raise AttributeError(
            f"Unsupported list method {method!r}. See README for the 10 supported list operations."
        )

    @staticmethod
    def _evaluate_mapping_method(values: dict[object, object], method: str, arguments: list[object]) -> object | None:
        """Implement the portable subset of Python dict and Java HashMap methods."""
        if method in {"get"}:
            if len(arguments) not in {1, 2}:
                raise TypeError("Map.get() expects a key and optional default")
            return values.get(arguments[0], arguments[1] if len(arguments) == 2 else None)
        if method in {"put", "set"}:
            if len(arguments) != 2:
                raise TypeError(f"Map.{method}() expects a key and value")
            previous = values.get(arguments[0])
            values[arguments[0]] = arguments[1]
            return previous
        if method in {"containsKey", "contains"}:
            if len(arguments) != 1:
                raise TypeError(f"Map.{method}() expects one key")
            return arguments[0] in values
        if method == "remove":
            if len(arguments) != 1:
                raise TypeError("Map.remove() expects one key")
            return values.pop(arguments[0], None)
        if method == "pop":
            if len(arguments) not in {1, 2}:
                raise TypeError("Map.pop() expects a key and optional default")
            if arguments[0] not in values and len(arguments) == 1:
                raise KeyError(arguments[0])
            return values.pop(arguments[0], arguments[1] if len(arguments) == 2 else None)
        if method in {"update", "putAll"}:
            if len(arguments) != 1 or not isinstance(arguments[0], dict):
                raise TypeError(f"Map.{method}() expects one dictionary")
            values.update(arguments[0])
            return None
        if method in {"size", "length"}:
            if arguments:
                raise TypeError(f"Map.{method}() expects no arguments")
            return len(values)
        if method == "keys":
            if arguments:
                raise TypeError("Map.keys() expects no arguments")
            return list(values.keys())
        if method == "values":
            if arguments:
                raise TypeError("Map.values() expects no arguments")
            return list(values.values())
        if method == "items":
            if arguments:
                raise TypeError("Map.items() expects no arguments")
            return list(values.items())
        if method == "clear":
            if arguments:
                raise TypeError("Map.clear() expects no arguments")
            values.clear()
            return None
        raise AttributeError("Supported map methods are get(), put()/set(), containsKey(), remove(), size(), keys(), values(), and clear()")

    @staticmethod
    def _evaluate_set_method(values: set[object], method: str, arguments: list[object]) -> object | None:
        """Implement the portable subset of Python set and Java HashSet methods."""
        if method == "add":
            if len(arguments) != 1:
                raise TypeError("Set.add() expects one value")
            values.add(arguments[0])
            return None
        if method == "remove":
            if len(arguments) != 1:
                raise TypeError("Set.remove() expects one value")
            values.discard(arguments[0])
            return None
        if method in {"contains", "__contains__"}:
            if len(arguments) != 1:
                raise TypeError("Set.contains() expects one value")
            return arguments[0] in values
        if method in {"size", "length"}:
            if arguments:
                raise TypeError(f"Set.{method}() expects no arguments")
            return len(values)
        if method == "clear":
            if arguments:
                raise TypeError("Set.clear() expects no arguments")
            values.clear()
            return None
        raise AttributeError("Supported set methods are add(), remove(), contains(), size(), and clear()")

    @staticmethod
    def _list_index(value: object, method: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"List.{method}() index must be an integer")
        return value

    def _instantiate(self, class_name: str, arguments: list[object]) -> ObjectInstance:
        instance = self.classes.instantiate(class_name)
        self.classes.call_constructor(instance, arguments, self._execute_method)
        return instance

    def _evaluate_scanner_call(self, method: str, arguments: list[object]) -> object:
        """Implement the useful no-argument Java Scanner read methods."""
        if arguments:
            raise TypeError(f"Scanner.{method}() does not accept arguments in this subset")
        converters: Mapping[str, Callable[[str], object]] = {
            "nextInt": int,
            "nextDouble": float,
            "nextLine": lambda value: value,
        }
        if method not in converters:
            raise AttributeError(f"Unsupported Scanner method {method!r}; use nextInt(), nextDouble(), or nextLine()")
        return self._convert_input(self._read_text(""), converters[method], f"Scanner.{method}()")

    def _read_text(self, prompt: str) -> str:
        value = self.input_reader(prompt)
        if not isinstance(value, str):
            raise TypeError("Input reader must return text")
        return value

    @staticmethod
    def _convert_input(value: str, converter: Callable[[str], object], label: str) -> object:
        try:
            return converter(value)
        except ValueError as error:
            raise ValueError(f"{label} could not convert input {value!r}") from error

    def _convert_cpp_input(self, target: Expression, value: str) -> object:
        """Use a prior C++ declaration to choose a sensible ``cin`` conversion."""
        declared_type = self._variable_types.get(target.name) if isinstance(target, Identifier) else None
        converters: Mapping[str, Callable[[str], object]] = {
            "int": int,
            "float": float,
            "bool": lambda text: {"true": True, "false": False}[text.lower()],
            "string": lambda text: text,
        }
        converter = converters.get(declared_type or "", lambda text: text)
        return self._convert_input(value, converter, "cin")

    def _execute_function(self, body: object, table: SymbolTable) -> None:
        if not isinstance(body, Block):
            raise TypeError("Function body must be an AST block")
        label = table.current_scope_name.removeprefix("function:")
        if self._call_depth >= self.max_call_depth:
            raise CallDepthExceeded(self.max_call_depth, [*self._call_stack, f"{label}()"])
        self._call_depth += 1
        self._call_stack.append(f"{label}()")
        try:
            self._evaluate_block(body)
        finally:
            self._call_stack.pop()
            self._call_depth -= 1

    def _execute_method(self, body: object, context: MethodContext) -> object | None:
        if not isinstance(body, Block):
            raise TypeError("Method body must be an AST block")
        label = f"{context.owner_class or context.instance.class_name} method"
        if self._call_depth >= self.max_call_depth:
            raise CallDepthExceeded(self.max_call_depth, [*self._call_stack, label])
        self._call_depth += 1
        self._call_stack.append(label)
        try:
            with self.symbols.scope(f"method:{context.instance.class_name}"):
                for name, value in context.bindings.items():
                    self.symbols.define(name, value)
                self._active_instances.append(context.instance)
                if context.is_constructor:
                    if context.owner_class is None:
                        raise RuntimeError("Constructor context requires an owner class")
                    self._active_constructor_classes.append(context.owner_class)
                try:
                    return self._evaluate_block(body)
                except ReturnSignal as signal:
                    return signal.value
                finally:
                    if context.is_constructor:
                        self._active_constructor_classes.pop()
                    self._active_instances.pop()
        finally:
            self._call_stack.pop()
            self._call_depth -= 1

    def _register_class(self, declaration: ClassDeclaration) -> None:
        attributes = {
            attribute.name: self.evaluate(attribute.value) if attribute.value is not None else None
            for attribute in declaration.attributes
        }
        methods = {
            method.name: MethodDefinition(tuple(method.parameters), method.body, tuple(method.parameter_types))
            for method in declaration.methods if not method.is_static
        }
        static_methods = {
            method.name: MethodDefinition(tuple(method.parameters), method.body, tuple(method.parameter_types))
            for method in declaration.methods if method.is_static
        }
        overloads: dict[str, tuple[MethodDefinition, ...]] = {}
        static_overloads: dict[str, tuple[MethodDefinition, ...]] = {}
        for method in declaration.methods:
            definition = MethodDefinition(tuple(method.parameters), method.body, tuple(method.parameter_types))
            target = static_overloads if method.is_static else overloads
            target[method.name] = (*target.get(method.name, ()), definition)
        if len(declaration.constructors) > 1:
            raise ValueError(f"Class {declaration.name!r} has more than one constructor")
        constructor = (
            MethodDefinition(tuple(declaration.constructors[0].parameters), declaration.constructors[0].body, tuple(declaration.constructors[0].parameter_types))
            if declaration.constructors else None
        )
        self.classes.register(
            declaration.name, attributes=attributes, methods=methods,
            constructor=constructor, parent_name=declaration.parent_name,
            static_attributes={
                attribute.name: self.evaluate(attribute.value) if attribute.value is not None else None
                for attribute in declaration.static_attributes
            },
            static_methods=static_methods,
            method_overloads=overloads,
            static_method_overloads=static_overloads,
        )

    def _evaluate_unary(self, node: UnaryOperation) -> object:
        operand = self.evaluate(node.operand)
        if node.operator == "-":
            return -operand
        if node.operator in {"!", "not"}:
            return not self._truthy(operand)
        raise ValueError(f"Unsupported unary operator {node.operator!r}")

    def _evaluate_binary(self, node: BinaryOperation) -> object:
        if node.operator in {"and", "&&"}:
            left = self.evaluate(node.left)
            return self.evaluate(node.right) if self._truthy(left) else left
        if node.operator in {"or", "||"}:
            left = self.evaluate(node.left)
            return left if self._truthy(left) else self.evaluate(node.right)

        left = self.evaluate(node.left)
        right = self.evaluate(node.right)
        operators: Mapping[str, Callable[[object, object], object]] = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b,
            "%": lambda a, b: a % b,
            "in": lambda a, b: a in b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }
        try:
            return operators[node.operator](left, right)
        except KeyError as error:
            raise ValueError(f"Unsupported binary operator {node.operator!r}") from error

    @staticmethod
    def _truthy(value: object) -> bool:
        return bool(value)
