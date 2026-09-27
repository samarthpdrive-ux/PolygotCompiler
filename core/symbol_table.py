"""Hierarchical variable and function scopes for Phase 3.

The table is runtime-neutral: a future evaluator can use it for Python, C++,
or Java AST nodes without duplicating scope rules in each front end.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FunctionDefinition:
    """Language-independent metadata for a parsed function."""

    name: str
    parameters: tuple[str, ...]
    body: object
    parameter_types: tuple[str, ...] = ()
    parameter_by_reference: tuple[bool, ...] = ()


@dataclass(slots=True)
class ReferenceBinding:
    """A parameter aliasing a caller binding for C++ ``T&`` semantics."""

    values: dict[str, object]
    name: str

    def get(self) -> object:
        return self.values[self.name]

    def set(self, value: object) -> None:
        self.values[self.name] = value


@dataclass(slots=True)
class ScopeFrame:
    """One level of variable and function bindings."""

    label: str
    values: dict[str, object] = field(default_factory=dict)
    functions: dict[str, list[FunctionDefinition]] = field(default_factory=dict)


class ReturnSignal(Exception):
    """Internal control-flow signal caught at a function-call boundary."""

    def __init__(self, value: object | None) -> None:
        self.value = value
        super().__init__("function return")


FunctionExecutor = Callable[[object, "SymbolTable"], None]


class SymbolTable:
    """A stack of scopes with variable lookup and function-call support."""

    def __init__(self) -> None:
        self._frames: list[ScopeFrame] = [ScopeFrame("global")]

    @property
    def scope_depth(self) -> int:
        """Return the number of active scopes, including the global scope."""
        return len(self._frames)

    @property
    def current_scope_name(self) -> str:
        """Return a human-readable label for the innermost active scope."""
        return self._frames[-1].label

    def define(self, name: str, value: object) -> None:
        """Create or replace a binding in the current scope only."""
        self._validate_name(name)
        self._frames[-1].values[name] = value

    def define_reference(self, name: str, target_name: str) -> None:
        """Bind ``name`` to the nearest caller variable named ``target_name``."""
        self._validate_name(name)
        for frame in reversed(self._frames):
            if target_name in frame.values:
                value = frame.values[target_name]
                if isinstance(value, ReferenceBinding):
                    self._frames[-1].values[name] = value
                else:
                    self._frames[-1].values[name] = ReferenceBinding(frame.values, target_name)
                return
        raise NameError(f"Variable {target_name!r} is not defined")

    def assign(self, name: str, value: object) -> None:
        """Update the nearest existing variable binding.

        Assigning an undefined name is an error. This makes accidental global
        variable creation explicit instead of silently leaking local state.
        """
        for frame in reversed(self._frames):
            if name in frame.values:
                existing = frame.values[name]
                if isinstance(existing, ReferenceBinding):
                    existing.set(value)
                else:
                    frame.values[name] = value
                return
        raise NameError(f"Variable {name!r} is not defined")

    def lookup(self, name: str) -> object:
        """Find a variable by searching from local scope to global scope."""
        for frame in reversed(self._frames):
            if name in frame.values:
                value = frame.values[name]
                return value.get() if isinstance(value, ReferenceBinding) else value
        raise NameError(f"Variable {name!r} is not defined")

    def is_defined(self, name: str) -> bool:
        """Return whether a variable is visible in the current scope chain."""
        return any(name in frame.values for frame in reversed(self._frames))

    def global_bindings(self) -> dict[str, object]:
        """Return a copy of the program's global variable bindings for the CLI."""
        return {name: value.get() if isinstance(value, ReferenceBinding) else value for name, value in self._frames[0].values.items()}

    def define_function(
        self, name: str, parameters: Sequence[str], body: object,
        parameter_types: Sequence[str] = (), parameter_by_reference: Sequence[bool] = (),
    ) -> FunctionDefinition:
        """Register a function in the current scope.

        ``body`` is left opaque so Phase 4/5 can store the relevant AST block
        regardless of the source language that produced it.
        """
        self._validate_name(name)
        parameter_names = tuple(parameters)
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError(f"Function {name!r} has duplicate parameter names")
        for parameter in parameter_names:
            self._validate_name(parameter)

        definition = FunctionDefinition(name, parameter_names, body, tuple(parameter_types), tuple(parameter_by_reference))
        overloads = self._frames[-1].functions.setdefault(name, [])
        if any(len(existing.parameters) == len(parameter_names) for existing in overloads):
            raise ValueError(f"Function {name!r} already has an overload with {len(parameter_names)} parameter(s)")
        overloads.append(definition)
        return definition

    def get_function(self, name: str, arity: int | None = None, argument_types: Sequence[str] | None = None) -> FunctionDefinition:
        """Find a function by searching from local scope to global scope."""
        for frame in reversed(self._frames):
            if name in frame.functions:
                overloads = frame.functions[name]
                if arity is None:
                    return overloads[0]
                candidates = [definition for definition in overloads if len(definition.parameters) == arity]
                if argument_types is not None:
                    exact = [definition for definition in candidates if definition.parameter_types == tuple(argument_types)]
                    if exact:
                        return exact[0]
                if candidates:
                    return candidates[0]
                available = ", ".join(str(len(item.parameters)) for item in overloads)
                raise TypeError(f"No overload for {name}() accepts {arity} argument(s); available arities: {available}")
        raise NameError(f"Function {name!r} is not defined")

    def is_function_defined(self, name: str) -> bool:
        """Return whether a function is visible in the current scope chain."""
        return any(name in frame.functions for frame in reversed(self._frames))

    def call_function(
        self,
        function: str | FunctionDefinition,
        arguments: Sequence[object],
        executor: FunctionExecutor,
    ) -> object | None:
        """Run a function body with a temporary parameter scope.

        The supplied executor will later be the unified AST evaluator. For
        Phase 3 it is a small callback, allowing scope and return behaviour to
        be tested without introducing execution semantics prematurely.
        """
        definition = self.get_function(function) if isinstance(function, str) else function
        if len(arguments) != len(definition.parameters):
            raise TypeError(
                f"{definition.name}() expects {len(definition.parameters)} argument(s), "
                f"got {len(arguments)}"
            )

        with self.scope(f"function:{definition.name}"):
            for index, (parameter, argument) in enumerate(zip(definition.parameters, arguments, strict=True)):
                if index < len(definition.parameter_by_reference) and definition.parameter_by_reference[index]:
                    if not isinstance(argument, str):
                        raise TypeError(f"Reference parameter {parameter!r} requires a variable name")
                    self.define_reference(parameter, argument)
                else:
                    self.define(parameter, argument)
            try:
                executor(definition.body, self)
            except ReturnSignal as signal:
                return signal.value
        return None

    def return_from_function(self, value: object | None = None) -> None:
        """Stop the current function executor and return ``value`` to its caller."""
        raise ReturnSignal(value)

    @contextmanager
    def scope(self, label: str = "block") -> Iterator["SymbolTable"]:
        """Push a temporary scope and remove it even if evaluation fails."""
        self._frames.append(ScopeFrame(label))
        try:
            yield self
        finally:
            self._frames.pop()

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not name.isidentifier():
            raise ValueError(f"Invalid identifier {name!r}")
