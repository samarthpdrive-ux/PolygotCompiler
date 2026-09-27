"""Stack bytecode compiler and VM for the shared polyglot AST.

The bytecode path supports variables, expressions, control flow, functions,
classes, fields, constructors, inheritance, and method dispatch.  The normal
evaluator remains the reference implementation for language-specific library
features.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter

from .ast_nodes import (
    ArrayDeclaration, Assignment, BinaryOperation, Block, BooleanLiteral,
    CallExpression, ClassDeclaration, Expression, ExpressionStatement,
    ForEachStatement, ForStatement, FunctionDeclaration, Identifier, IfStatement,
    IndexAccess, ListLiteral, MemberAccess, NewExpression, NullLiteral, NumberLiteral,
    ObjectDeclaration, OutputStatement, Program, ReturnStatement, StringLiteral, SuperConstructorCall,
    UnaryOperation, VariableDeclaration, WhileStatement,
)
from .oop import ObjectInstance
from runtime.errors import CallDepthExceeded


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: str
    operand: object | None = None


@dataclass(frozen=True, slots=True)
class BytecodeFunction:
    parameters: tuple[str, ...]
    instructions: tuple[Instruction, ...]
    parameter_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BytecodeClass:
    name: str
    field_initializers: dict[str, tuple[Instruction, ...]] = field(default_factory=dict)
    methods: dict[str, tuple[BytecodeFunction, ...]] = field(default_factory=dict)
    constructors: tuple[BytecodeFunction, ...] = ()
    parent_name: str | None = None
    static_fields: dict[str, tuple[Instruction, ...]] = field(default_factory=dict)
    static_methods: dict[str, tuple[BytecodeFunction, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BytecodeModule:
    main: tuple[Instruction, ...]
    functions: dict[str, BytecodeFunction]
    classes: dict[str, BytecodeClass] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BytecodeClassReference:
    name: str


class BytecodeCompiler:
    """Compile the shared AST into a small, inspectable instruction set."""

    def compile(self, program: Program) -> list[Instruction]:
        """Backward-compatible helper returning only the module main code."""
        return list(self.compile_module(program).main)

    def compile_module(self, program: Program) -> BytecodeModule:
        code: list[Instruction] = []
        functions: dict[str, BytecodeFunction] = {}
        classes: dict[str, BytecodeClass] = {}
        for statement in program.statements:
            if isinstance(statement, FunctionDeclaration):
                functions[statement.name] = self._compile_function(statement)
            elif isinstance(statement, ClassDeclaration):
                classes[statement.name] = self._compile_class(statement)
            else:
                self._statement(statement, code)
        return BytecodeModule(tuple(code), functions, classes)

    def _compile_function(self, declaration: FunctionDeclaration) -> BytecodeFunction:
        code: list[Instruction] = []
        self._statement(declaration.body, code)
        if not code or code[-1].opcode != "RETURN":
            code.extend((Instruction("PUSH", None), Instruction("RETURN")))
        return BytecodeFunction(
            tuple(declaration.parameters), tuple(code), tuple(declaration.parameter_types)
        )

    def _compile_class(self, declaration: ClassDeclaration) -> BytecodeClass:
        fields = {field.name: self._compile_initializer(field.value) for field in declaration.attributes}
        static_fields = {field.name: self._compile_initializer(field.value) for field in declaration.static_attributes}
        methods: dict[str, tuple[BytecodeFunction, ...]] = {}
        static_methods: dict[str, tuple[BytecodeFunction, ...]] = {}
        for method in declaration.methods:
            target = static_methods if method.is_static else methods
            compiled = self._compile_function(method)
            target[method.name] = (*target.get(method.name, ()), compiled)
        constructors = tuple(self._compile_function(item) for item in declaration.constructors)
        return BytecodeClass(
            declaration.name, fields, methods, constructors, declaration.parent_name,
            static_fields, static_methods,
        )

    def _compile_initializer(self, expression: Expression | None) -> tuple[Instruction, ...]:
        code: list[Instruction] = []
        if expression is None:
            code.append(Instruction("PUSH", None))
        else:
            self._expression(expression, code)
        code.append(Instruction("STORE", "__field_value__"))
        return tuple(code)

    def _statement(self, statement: object, code: list[Instruction]) -> None:
        if isinstance(statement, VariableDeclaration):
            self._expression(statement.value, code) if statement.value is not None else code.append(Instruction("PUSH", None))
            code.append(Instruction("DECLARE", statement.name))
        elif isinstance(statement, ArrayDeclaration):
            for value in statement.values or []:
                self._expression(value, code)
            code.append(Instruction("BUILD_LIST", len(statement.values or [])))
            code.append(Instruction("DECLARE", statement.name))
        elif isinstance(statement, Assignment):
            if isinstance(statement.target, Identifier):
                self._expression(statement.value, code)
                code.append(Instruction("STORE", statement.target.name))
            elif isinstance(statement.target, MemberAccess):
                self._expression(statement.target.object, code)
                self._expression(statement.value, code)
                code.append(Instruction("SET_MEMBER", statement.target.member))
            elif isinstance(statement.target, IndexAccess):
                self._expression(statement.target.object, code)
                self._expression(statement.target.index, code)
                self._expression(statement.value, code)
                code.append(Instruction("SET_INDEX"))
            else:
                raise ValueError(f"Bytecode mode does not support assignment target {type(statement.target).__name__}.")
        elif isinstance(statement, ObjectDeclaration):
            for argument in statement.constructor_arguments:
                self._expression(argument, code)
            code.append(Instruction("NEW", (statement.class_name, len(statement.constructor_arguments))))
            code.append(Instruction("DECLARE", statement.name))
        elif isinstance(statement, ExpressionStatement):
            self._expression(statement.expression, code)
            code.append(Instruction("POP"))
        elif isinstance(statement, OutputStatement):
            for value in statement.values:
                self._expression(value, code)
            code.append(Instruction("PRINT", len(statement.values)))
        elif isinstance(statement, ReturnStatement):
            self._expression(statement.value, code) if statement.value is not None else code.append(Instruction("PUSH", None))
            code.append(Instruction("RETURN"))
        elif isinstance(statement, SuperConstructorCall):
            for argument in statement.arguments:
                self._expression(argument, code)
            code.append(Instruction("SUPER_CALL", len(statement.arguments)))
        elif isinstance(statement, Block):
            for child in statement.statements:
                self._statement(child, code)
        elif isinstance(statement, IfStatement):
            self._expression(statement.condition, code)
            false_jump = len(code)
            code.append(Instruction("JUMP_IF_FALSE", None))
            self._statement(statement.then_branch, code)
            end_jump = len(code)
            code.append(Instruction("JUMP", None))
            code[false_jump] = Instruction("JUMP_IF_FALSE", len(code))
            if statement.else_branch is not None:
                self._statement(statement.else_branch, code)
            code[end_jump] = Instruction("JUMP", len(code))
        elif isinstance(statement, WhileStatement):
            start = len(code)
            self._expression(statement.condition, code)
            exit_jump = len(code)
            code.append(Instruction("JUMP_IF_FALSE", None))
            self._statement(statement.body, code)
            code.append(Instruction("JUMP", start))
            code[exit_jump] = Instruction("JUMP_IF_FALSE", len(code))
        elif isinstance(statement, ForStatement):
            self._statement(statement.initializer, code)
            start = len(code)
            self._expression(statement.condition, code)
            exit_jump = len(code)
            code.append(Instruction("JUMP_IF_FALSE", None))
            self._statement(statement.body, code)
            self._statement(statement.update, code)
            code.append(Instruction("JUMP", start))
            code[exit_jump] = Instruction("JUMP_IF_FALSE", len(code))
        elif isinstance(statement, ForEachStatement):
            self._expression(statement.iterable, code)
            code.append(Instruction("ITER_INIT"))
            next_index = len(code)
            code.append(Instruction("ITER_NEXT", (statement.name, None)))
            self._statement(statement.body, code)
            code.append(Instruction("JUMP", next_index))
            code[next_index] = Instruction("ITER_NEXT", (statement.name, len(code)))
        else:
            raise ValueError(f"Bytecode mode does not support {type(statement).__name__}.")

    def _expression(self, expression: Expression, code: list[Instruction]) -> None:
        if isinstance(expression, NumberLiteral | BooleanLiteral | StringLiteral):
            code.append(Instruction("PUSH", expression.value))
        elif isinstance(expression, NullLiteral):
            code.append(Instruction("PUSH", None))
        elif isinstance(expression, ListLiteral):
            for element in expression.elements:
                self._expression(element, code)
            code.append(Instruction("BUILD_LIST", len(expression.elements)))
        elif isinstance(expression, Identifier):
            code.append(Instruction("LOAD", expression.name))
        elif isinstance(expression, UnaryOperation):
            self._expression(expression.operand, code)
            code.append(Instruction("UNARY", expression.operator))
        elif isinstance(expression, BinaryOperation):
            self._expression(expression.left, code)
            self._expression(expression.right, code)
            code.append(Instruction("BINARY", expression.operator))
        elif isinstance(expression, MemberAccess):
            self._expression(expression.object, code)
            code.append(Instruction("GET_MEMBER", expression.member))
        elif isinstance(expression, IndexAccess):
            self._expression(expression.object, code)
            self._expression(expression.index, code)
            code.append(Instruction("GET_INDEX"))
        elif isinstance(expression, NewExpression):
            for argument in expression.arguments:
                self._expression(argument, code)
            code.append(Instruction("NEW", (expression.class_name, len(expression.arguments))))
        elif isinstance(expression, CallExpression) and isinstance(expression.callee, Identifier) and expression.callee.name == "print":
            for argument in expression.arguments:
                self._expression(argument, code)
            code.append(Instruction("PRINT", len(expression.arguments)))
            code.append(Instruction("PUSH", None))
        elif (
            isinstance(expression, CallExpression)
            and isinstance(expression.callee, MemberAccess)
            and expression.callee.member in {"print", "println"}
            and isinstance(expression.callee.object, MemberAccess)
            and expression.callee.object.member == "out"
            and isinstance(expression.callee.object.object, Identifier)
            and expression.callee.object.object.name == "System"
        ):
            for argument in expression.arguments:
                self._expression(argument, code)
            code.append(Instruction("PRINT", len(expression.arguments)))
            code.append(Instruction("PUSH", None))
        elif isinstance(expression, CallExpression) and isinstance(expression.callee, Identifier):
            for argument in expression.arguments:
                self._expression(argument, code)
            code.append(Instruction("CALL", (expression.callee.name, len(expression.arguments))))
        elif isinstance(expression, CallExpression) and isinstance(expression.callee, MemberAccess):
            self._expression(expression.callee.object, code)
            for argument in expression.arguments:
                self._expression(argument, code)
            code.append(Instruction("CALL_METHOD", (expression.callee.member, len(expression.arguments))))
        else:
            raise ValueError(f"Bytecode mode does not support {type(expression).__name__}.")


class BytecodeOptimizer:
    """Apply conservative, semantics-preserving bytecode optimizations."""

    def optimize(self, module: BytecodeModule) -> BytecodeModule:
        return BytecodeModule(
            self._optimize_code(module.main),
            {name: self._optimize_function(function) for name, function in module.functions.items()},
            {name: self._optimize_class(cls) for name, cls in module.classes.items()},
        )

    def _optimize_class(self, cls: BytecodeClass) -> BytecodeClass:
        return BytecodeClass(
            cls.name,
            {name: self._optimize_code(code) for name, code in cls.field_initializers.items()},
            {name: tuple(self._optimize_function(item) for item in methods) for name, methods in cls.methods.items()},
            tuple(self._optimize_function(item) for item in cls.constructors),
            cls.parent_name,
            {name: self._optimize_code(code) for name, code in cls.static_fields.items()},
            {name: tuple(self._optimize_function(item) for item in methods) for name, methods in cls.static_methods.items()},
        )

    def _optimize_function(self, function: BytecodeFunction) -> BytecodeFunction:
        return BytecodeFunction(function.parameters, self._optimize_code(function.instructions), function.parameter_types)

    def _optimize_code(self, code: tuple[Instruction, ...]) -> tuple[Instruction, ...]:
        current = list(code)
        # A few passes let one fold expose another fold. Every shrinking pass
        # relocates jump targets before the next pass begins.
        for _ in range(4):
            folded, folded_map = self._fold_constants(current)
            folded = self._relocate(folded, folded_map, len(current))
            cleaned, cleanup_map = self._remove_redundant(folded)
            cleaned = self._relocate(cleaned, cleanup_map, len(folded))
            reachable, reachability_map = self._remove_unreachable(cleaned)
            reachable = self._relocate(reachable, reachability_map, len(cleaned))
            if reachable == current:
                break
            current = reachable
        return tuple(current)

    def _fold_constants(self, code: list[Instruction]) -> tuple[list[Instruction], dict[int, int]]:
        output: list[Instruction] = []
        mapping: dict[int, int] = {}
        targets = self._jump_targets(code)
        index = 0
        while index < len(code):
            first = code[index]
            if (
                index + 2 < len(code)
                and first.opcode == "PUSH"
                and code[index + 1].opcode == "PUSH"
                and code[index + 2].opcode == "BINARY"
                and not targets.intersection({index + 1, index + 2})
            ):
                value = self._binary_value(first.operand, code[index + 1].operand, str(code[index + 2].operand))
                if value is not _NOT_FOLDABLE:
                    replacement = len(output)
                    output.append(Instruction("PUSH", value))
                    mapping.update({index: replacement, index + 1: replacement, index + 2: replacement})
                    index += 3
                    continue
            if index + 1 < len(code) and first.opcode == "PUSH" and code[index + 1].opcode == "UNARY" and index + 1 not in targets:
                value = self._unary_value(first.operand, str(code[index + 1].operand))
                if value is not _NOT_FOLDABLE:
                    replacement = len(output)
                    output.append(Instruction("PUSH", value))
                    mapping.update({index: replacement, index + 1: replacement})
                    index += 2
                    continue
            mapping[index] = len(output)
            output.append(first)
            index += 1
        return output, mapping

    @staticmethod
    def _binary_value(left: object, right: object, operator: str) -> object:
        operations = {
            "+": lambda: left + right, "-": lambda: left - right,
            "*": lambda: left * right, "/": lambda: left / right,
            "%": lambda: left % right, "==": lambda: left == right,
            "!=": lambda: left != right, "<": lambda: left < right,
            "<=": lambda: left <= right, ">": lambda: left > right,
            ">=": lambda: left >= right, "&&": lambda: bool(left and right),
            "||": lambda: bool(left or right),
        }
        try:
            return operations[operator]()
        except (KeyError, TypeError, ZeroDivisionError):
            return _NOT_FOLDABLE

    @staticmethod
    def _unary_value(value: object, operator: str) -> object:
        try:
            if operator == "-":
                return -value
            if operator in {"!", "not"}:
                return not value
        except TypeError:
            pass
        return _NOT_FOLDABLE

    @staticmethod
    def _remove_redundant(code: list[Instruction]) -> tuple[list[Instruction], dict[int, int]]:
        """Remove only instruction sequences without control-flow targets."""
        output: list[Instruction] = []
        mapping: dict[int, int] = {}
        targets = BytecodeOptimizer._jump_targets(code)
        index = 0
        while index < len(code):
            instruction = code[index]
            if instruction.opcode == "JUMP" and instruction.operand == index + 1:
                # A jump to the following instruction is a true no-op. Map a
                # possible external jump to this location onto that successor.
                mapping[index] = len(output)
                index += 1
                continue
            # PRINT/PUSH(None)/POP is emitted for an expression-form print;
            # only PRINT is observable.
            if (
                index + 2 < len(code)
                and instruction.opcode == "PRINT"
                and code[index + 1] == Instruction("PUSH", None)
                and code[index + 2].opcode == "POP"
                and not targets.intersection({index + 1, index + 2})
            ):
                replacement = len(output)
                output.append(instruction)
                mapping.update({index: replacement, index + 1: replacement, index + 2: replacement})
                index += 3
                continue
            mapping[index] = len(output)
            output.append(instruction)
            index += 1
        return output, mapping

    @staticmethod
    def _jump_targets(code: list[Instruction]) -> set[int]:
        targets: set[int] = set()
        for instruction in code:
            if instruction.opcode in {"JUMP", "JUMP_IF_FALSE"} and isinstance(instruction.operand, int):
                targets.add(instruction.operand)
            elif instruction.opcode == "ITER_NEXT" and isinstance(instruction.operand, tuple):
                targets.add(int(instruction.operand[1]))
        return targets

    @staticmethod
    def _relocate(code: list[Instruction], mapping: dict[int, int], old_length: int) -> list[Instruction]:
        """Update control-flow operands after an instruction shrinking pass."""
        mapping[old_length] = len(code)
        relocated: list[Instruction] = []
        for instruction in code:
            if instruction.opcode in {"JUMP", "JUMP_IF_FALSE"} and isinstance(instruction.operand, int):
                relocated.append(Instruction(instruction.opcode, mapping[instruction.operand]))
            elif instruction.opcode == "ITER_NEXT" and isinstance(instruction.operand, tuple):
                name, target = instruction.operand
                relocated.append(Instruction("ITER_NEXT", (name, mapping[int(target)])))
            else:
                relocated.append(instruction)
        return relocated

    @staticmethod
    def _remove_unreachable(code: list[Instruction]) -> tuple[list[Instruction], dict[int, int]]:
        """Remove code unreachable from the block entry, including after return."""
        if not code:
            return [], {}
        reachable: set[int] = set()
        pending = [0]
        while pending:
            index = pending.pop()
            if index in reachable or not 0 <= index < len(code):
                continue
            reachable.add(index)
            instruction = code[index]
            if instruction.opcode == "RETURN":
                continue
            if instruction.opcode == "JUMP":
                pending.append(int(instruction.operand))
            elif instruction.opcode in {"JUMP_IF_FALSE", "ITER_NEXT"}:
                target = instruction.operand if instruction.opcode == "JUMP_IF_FALSE" else instruction.operand[1]
                pending.extend((index + 1, int(target)))
            else:
                pending.append(index + 1)
        mapping: dict[int, int] = {}
        output: list[Instruction] = []
        for index, instruction in enumerate(code):
            if index in reachable:
                mapping[index] = len(output)
                output.append(instruction)
        return output, mapping


_NOT_FOLDABLE = object()


def disassemble(module: BytecodeModule) -> str:
    """Render bytecode in a stable form suitable for reports and debugging."""
    sections = ["== main ==", _format_code(module.main)]
    for name, function in sorted(module.functions.items()):
        sections.extend((f"== function {name}({', '.join(function.parameters)}) ==", _format_code(function.instructions)))
    for name, cls in sorted(module.classes.items()):
        sections.append(f"== class {name} ==")
        for method_name, overloads in sorted(cls.methods.items()):
            for index, method in enumerate(overloads, start=1):
                suffix = f"#{index}" if len(overloads) > 1 else ""
                sections.extend((f"-- method {method_name}{suffix}({', '.join(method.parameters)}) --", _format_code(method.instructions)))
        for index, constructor in enumerate(cls.constructors, start=1):
            suffix = f"#{index}" if len(cls.constructors) > 1 else ""
            sections.extend((f"-- constructor {name}{suffix}({', '.join(constructor.parameters)}) --", _format_code(constructor.instructions)))
        for method_name, overloads in sorted(cls.static_methods.items()):
            for index, method in enumerate(overloads, start=1):
                suffix = f"#{index}" if len(overloads) > 1 else ""
                sections.extend((f"-- static {method_name}{suffix}({', '.join(method.parameters)}) --", _format_code(method.instructions)))
    return "\n".join(section for section in sections if section)


def _format_code(code: tuple[Instruction, ...]) -> str:
    if not code:
        return "  <empty>"
    return "\n".join(
        f"  {index:04d}  {instruction.opcode}" + (f" {instruction.operand!r}" if instruction.operand is not None else "")
        for index, instruction in enumerate(code)
    )


class BytecodeVM:
    """Execute bytecode with isolated call frames and object instances."""

    def __init__(self, *, output: Callable[..., None] = print, trace: Callable[[str], None] | None = None, profiler: object | None = None, max_call_depth: int = 200) -> None:
        if max_call_depth <= 0:
            raise ValueError("max_call_depth must be positive")
        self.values: dict[str, object] = {}
        self.output = output
        self.trace = trace
        self.profiler = profiler
        self.functions: dict[str, BytecodeFunction] = {}
        self.classes: dict[str, BytecodeClass] = {}
        self._static_values: dict[tuple[str, str], object] = {}
        self._current_instance: ObjectInstance | None = None
        self._current_owner: str | None = None
        self.max_call_depth = max_call_depth
        self._call_depth = 0
        self._call_stack: list[str] = []

    def run(self, instructions: list[Instruction] | BytecodeModule) -> dict[str, object]:
        if isinstance(instructions, BytecodeModule):
            self.functions, self.classes = instructions.functions, instructions.classes
            self._execute(list(instructions.main), self.values)
        else:
            self._execute(instructions, self.values)
        return dict(self.values)

    def call_function(self, name: str, arguments: list[object] | None = None) -> object | None:
        return self._call_function(self.functions[name], arguments or [], label=name)

    def call_static(self, class_name: str, method_name: str, arguments: list[object] | None = None) -> object | None:
        method = self._select_method(self.classes[class_name].static_methods.get(method_name, ()), arguments or [], f"{class_name}.{method_name}")
        return self._call_function(method, arguments or [], owner=class_name, label=f"{class_name}.{method_name}")

    @staticmethod
    def _runtime_type(value: object) -> str:
        if isinstance(value, bool): return "boolean"
        if isinstance(value, int): return "int"
        if isinstance(value, float): return "double"
        if isinstance(value, str): return "String"
        return "unknown"

    def _call_function(self, function: BytecodeFunction, arguments: list[object], *, instance: ObjectInstance | None = None, owner: str | None = None, label: str | None = None) -> object | None:
        if len(arguments) != len(function.parameters):
            raise TypeError(f"Function expects {len(function.parameters)} argument(s), got {len(arguments)}")
        call_label = label or owner or "function"
        if self._call_depth >= self.max_call_depth:
            raise CallDepthExceeded(self.max_call_depth, [*self._call_stack, f"{call_label}()"])
        frame = dict(zip(function.parameters, arguments, strict=True))
        if instance is not None:
            frame.update({"self": instance, "this": instance})
        previous_instance, previous_owner = self._current_instance, self._current_owner
        self._current_instance, self._current_owner = instance, owner or (instance.class_name if instance else None)
        self._call_depth += 1
        self._call_stack.append(f"{call_label}()")
        try:
            _, value = self._execute(list(function.instructions), frame)
            return value
        finally:
            self._call_stack.pop()
            self._call_depth -= 1
            self._current_instance, self._current_owner = previous_instance, previous_owner

    def _execute(self, instructions: list[Instruction], locals_: dict[str, object]) -> tuple[bool, object | None]:
        stack: list[object] = []
        iterators: list[object] = []
        pc = 0
        while pc < len(instructions):
            instruction = instructions[pc]
            pc += 1
            if self.profiler is not None and hasattr(self.profiler, "record"):
                self.profiler.record(instruction.opcode)
            if self.trace is not None:
                self.trace(f"pc={pc - 1} {instruction.opcode} {instruction.operand!r}")
            opcode = instruction.opcode
            if opcode == "PUSH":
                stack.append(instruction.operand)
            elif opcode == "LOAD":
                name = str(instruction.operand)
                if name in locals_: value = locals_[name]
                elif self._current_instance is not None and name in self._current_instance.state: value = self._current_instance.get_attribute(name)
                elif name in self.values: value = self.values[name]
                elif name in self.classes: value = BytecodeClassReference(name)
                else: raise NameError(f"Variable {name!r} is not defined")
                stack.append(value)
            elif opcode == "DECLARE":
                locals_[str(instruction.operand)] = stack.pop()
            elif opcode == "STORE":
                name, value = str(instruction.operand), stack.pop()
                if name == "__field_value__": locals_[name] = value
                elif name in locals_ or self._current_instance is None or name not in self._current_instance.state: locals_[name] = value
                else: self._current_instance.set_attribute(name, value)
            elif opcode == "POP":
                if stack: stack.pop()
            elif opcode == "PRINT":
                count = int(instruction.operand)
                values = stack[-count:] if count else []
                if count: del stack[-count:]
                self.output(*values)
            elif opcode == "BUILD_LIST":
                count = int(instruction.operand)
                values = stack[-count:] if count else []
                if count: del stack[-count:]
                stack.append(values)
            elif opcode == "GET_INDEX":
                index, values = stack.pop(), stack.pop(); stack.append(values[index])
            elif opcode == "SET_INDEX":
                value, index, values = stack.pop(), stack.pop(), stack.pop(); values[index] = value
            elif opcode == "GET_MEMBER":
                stack.append(self._get_member(stack.pop(), str(instruction.operand)))
            elif opcode == "SET_MEMBER":
                value, receiver = stack.pop(), stack.pop(); self._set_member(receiver, str(instruction.operand), value); stack.append(value)
            elif opcode == "NEW":
                class_name, count = instruction.operand
                args = list(reversed([stack.pop() for _ in range(count)])); stack.append(self._instantiate(str(class_name), args))
            elif opcode == "CALL":
                name, count = instruction.operand
                args = list(reversed([stack.pop() for _ in range(count)]))
                if name in self.functions:
                    stack.append(self._call_function(self.functions[name], args, label=name))
                elif self._current_instance is not None:
                    stack.append(self._call_method(self._current_instance, str(name), args))
                else:
                    raise RuntimeError(f"Unknown bytecode function {name!r}")
            elif opcode == "CALL_METHOD":
                name, count = instruction.operand
                args = list(reversed([stack.pop() for _ in range(count)])); receiver = stack.pop()
                stack.append(self._call_method(receiver, str(name), args))
            elif opcode == "SUPER_CALL":
                count = int(instruction.operand)
                args = list(reversed([stack.pop() for _ in range(count)]))
                if self._current_instance is None or self._current_owner is None: raise RuntimeError("super constructor called outside a constructor")
                parent = self.classes[self._current_owner].parent_name
                if parent is None: raise RuntimeError(f"Class {self._current_owner!r} has no parent class")
                self._call_constructor(self._current_instance, parent, args)
            elif opcode == "RETURN":
                return True, stack.pop() if stack else None
            elif opcode == "JUMP":
                pc = int(instruction.operand)
            elif opcode == "JUMP_IF_FALSE":
                if not stack.pop(): pc = int(instruction.operand)
            elif opcode == "ITER_INIT":
                iterators.append(iter(stack.pop()))
            elif opcode == "ITER_NEXT":
                name, exit_pc = instruction.operand
                try: locals_[str(name)] = next(iterators[-1])
                except StopIteration: iterators.pop(); pc = int(exit_pc)
            elif opcode == "UNARY":
                value = stack.pop(); stack.append(-value if instruction.operand == "-" else not value)
            elif opcode == "BINARY":
                right, left = stack.pop(), stack.pop()
                operators = {"+": lambda: left + right, "-": lambda: left - right, "*": lambda: left * right, "/": lambda: left / right, "%": lambda: left % right, "==": lambda: left == right, "!=": lambda: left != right, "<": lambda: left < right, "<=": lambda: left <= right, ">": lambda: left > right, ">=": lambda: left >= right, "&&": lambda: bool(left and right), "||": lambda: bool(left or right)}
                try: stack.append(operators[str(instruction.operand)]())
                except KeyError as error: raise RuntimeError(f"Unknown binary operator {instruction.operand!r}") from error
            else:
                raise RuntimeError(f"Unknown bytecode instruction {opcode!r}")
        return False, None

    def _instantiate(self, class_name: str, arguments: list[object]) -> ObjectInstance:
        if class_name not in self.classes: raise NameError(f"Class {class_name!r} is not defined")
        instance = ObjectInstance(class_name, {})
        self._initialize_fields(class_name, instance)
        self._call_constructor(instance, class_name, arguments)
        return instance

    def _initialize_fields(self, class_name: str, instance: ObjectInstance) -> None:
        cls = self.classes[class_name]
        if cls.parent_name is not None: self._initialize_fields(cls.parent_name, instance)
        for name, initializer in cls.field_initializers.items():
            frame = {"self": instance, "this": instance}
            self._execute(list(initializer), frame)
            instance.state[name] = frame.get("__field_value__")

    def _call_constructor(self, instance: ObjectInstance, class_name: str, arguments: list[object]) -> object | None:
        cls = self.classes[class_name]
        if cls.parent_name is not None:
            explicit = bool(cls.constructors and any(item.opcode == "SUPER_CALL" for item in cls.constructors[0].instructions))
            if not explicit: self._call_constructor(instance, cls.parent_name, [])
        if not cls.constructors:
            if arguments: raise TypeError(f"{class_name} has no constructor accepting arguments")
            return None
        constructor = self._select_method(cls.constructors, arguments, f"{class_name} constructor")
        return self._call_function(constructor, arguments, instance=instance, owner=class_name, label=f"{class_name} constructor")

    def _call_method(self, receiver: object, name: str, arguments: list[object]) -> object | None:
        if isinstance(receiver, BytecodeClassReference):
            cls = self.classes[receiver.name]
            method = self._select_method(cls.static_methods.get(name, ()), arguments, f"{receiver.name}.{name}")
            return self._call_function(method, arguments, owner=receiver.name, label=f"{receiver.name}.{name}")
        if isinstance(receiver, (str, list, tuple, dict, set)):
            if name in {"length", "size"} and not arguments:
                return len(receiver)
            if name in {"append", "add"} and len(arguments) == 1 and isinstance(receiver, list):
                receiver.append(arguments[0]); return None
            raise AttributeError(f"Collection has no bytecode method {name!r}")
        if not isinstance(receiver, ObjectInstance): raise TypeError(f"Cannot call {name!r} on a non-object value")
        methods = self._find_methods(self.classes[receiver.class_name], name)
        method = self._select_method(methods, arguments, f"{receiver.class_name}.{name}")
        return self._call_function(method, arguments, instance=receiver, owner=self._owner_for_method(receiver.class_name, name, method), label=f"{receiver.class_name}.{name}")

    def _get_member(self, receiver: object, member: str) -> object:
        if isinstance(receiver, BytecodeClassReference):
            key = (receiver.name, member)
            if key not in self._static_values:
                cls = self.classes[receiver.name]
                if member not in cls.static_fields: raise AttributeError(f"{receiver.name} has no static field {member!r}")
                frame: dict[str, object] = {}; self._execute(list(cls.static_fields[member]), frame)
                self._static_values[key] = frame.get("__field_value__")
            return self._static_values[key]
        if isinstance(receiver, ObjectInstance): return receiver.get_attribute(member)
        if isinstance(receiver, (str, list, tuple, dict, set)) and member in {"length", "size"}: return len(receiver)
        raise AttributeError(f"Object has no member {member!r}")

    def _set_member(self, receiver: object, member: str, value: object) -> None:
        if isinstance(receiver, ObjectInstance): receiver.set_attribute(member, value); return
        if isinstance(receiver, BytecodeClassReference):
            if member not in self.classes[receiver.name].static_fields: raise AttributeError(f"{receiver.name} has no static field {member!r}")
            self._static_values[(receiver.name, member)] = value; return
        raise AttributeError(f"Object has no assignable member {member!r}")

    def _find_methods(self, cls: BytecodeClass, name: str) -> tuple[BytecodeFunction, ...]:
        if name in cls.methods: return cls.methods[name]
        if cls.parent_name is not None: return self._find_methods(self.classes[cls.parent_name], name)
        return ()

    def _owner_for_method(self, class_name: str, name: str, method: BytecodeFunction) -> str:
        cls = self.classes[class_name]
        if method in cls.methods.get(name, ()): return class_name
        if cls.parent_name is not None: return self._owner_for_method(cls.parent_name, name, method)
        return class_name

    def _select_method(self, methods: tuple[BytecodeFunction, ...], arguments: list[object], label: str) -> BytecodeFunction:
        if not methods: raise AttributeError(f"{label} is not defined")
        runtime_types = tuple(self._runtime_type(item) for item in arguments)
        for candidate in methods:
            if candidate.parameter_types and tuple(candidate.parameter_types) == runtime_types: return candidate
        for candidate in methods:
            if len(candidate.parameters) == len(arguments): return candidate
        raise TypeError(f"{label} received {len(arguments)} argument(s)")


class BytecodeProfiler:
    """Low-overhead opcode counter used by ``--profile``."""

    def __init__(self) -> None:
        self.started = perf_counter()
        self.opcode_counts: dict[str, int] = {}

    def record(self, opcode: str) -> None:
        self.opcode_counts[opcode] = self.opcode_counts.get(opcode, 0) + 1

    def report(self) -> str:
        elapsed_ms = (perf_counter() - self.started) * 1000
        total = sum(self.opcode_counts.values())
        lines = [f"Bytecode profile: {total} instructions in {elapsed_ms:.3f} ms"]
        lines.extend(f"  {opcode}: {count}" for opcode, count in sorted(self.opcode_counts.items()))
        return "\n".join(lines)
