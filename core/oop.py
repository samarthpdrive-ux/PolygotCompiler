"""Class blueprints, independent object state, and method dispatch for Phase 4."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .ast_nodes import BooleanLiteral, ClassDeclaration, FunctionDeclaration, NumberLiteral, SuperConstructorCall


@dataclass(frozen=True, slots=True)
class MethodDefinition:
    """A method blueprint independent of its source-language syntax."""

    parameters: tuple[str, ...]
    body: object
    parameter_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClassBlueprint:
    """A registry entry containing default attributes and method blueprints."""

    name: str
    attributes: Mapping[str, object]
    methods: Mapping[str, MethodDefinition]
    constructor: MethodDefinition | None = None
    parent_name: str | None = None
    static_attributes: dict[str, object] = field(default_factory=dict)
    static_methods: Mapping[str, MethodDefinition] = field(default_factory=dict)
    method_overloads: Mapping[str, tuple[MethodDefinition, ...]] = field(default_factory=dict)
    static_method_overloads: Mapping[str, tuple[MethodDefinition, ...]] = field(default_factory=dict)


@dataclass(slots=True)
class ObjectInstance:
    """One object allocation with state that is never shared with other instances."""

    class_name: str
    state: dict[str, object]

    def get_attribute(self, name: str) -> object:
        if name not in self.state:
            raise AttributeError(f"{self.class_name} has no attribute {name!r}")
        return self.state[name]

    def set_attribute(self, name: str, value: object) -> None:
        if name not in self.state:
            raise AttributeError(f"{self.class_name} has no attribute {name!r}")
        self.state[name] = value


@dataclass(frozen=True, slots=True)
class MethodContext:
    """Arguments supplied to a method, including both ``self`` and ``this``."""

    instance: ObjectInstance
    bindings: Mapping[str, object]
    owner_class: str | None = None
    is_constructor: bool = False

    def lookup(self, name: str) -> object:
        if name not in self.bindings:
            raise NameError(f"Method variable {name!r} is not defined")
        return self.bindings[name]


MethodExecutor = Callable[[object, MethodContext], object | None]


class ClassRegistry:
    """Stores class blueprints, creates objects, and routes method calls."""

    def __init__(self) -> None:
        self._classes: dict[str, ClassBlueprint] = {}

    def register(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
        methods: Mapping[str, MethodDefinition] | None = None,
        constructor: MethodDefinition | None = None,
        parent_name: str | None = None,
        static_attributes: Mapping[str, object] | None = None,
        static_methods: Mapping[str, MethodDefinition] | None = None,
        method_overloads: Mapping[str, tuple[MethodDefinition, ...]] | None = None,
        static_method_overloads: Mapping[str, tuple[MethodDefinition, ...]] | None = None,
    ) -> ClassBlueprint:
        """Add one class blueprint to the registry."""
        if not name or not name.isidentifier():
            raise ValueError(f"Invalid class name {name!r}")
        if name in self._classes:
            raise ValueError(f"Class {name!r} is already registered")
        inherited_attributes: dict[str, object] = {}
        inherited_methods: dict[str, MethodDefinition] = {}
        inherited_static_attributes: dict[str, object] = {}
        inherited_static_methods: dict[str, MethodDefinition] = {}
        inherited_overloads: dict[str, tuple[MethodDefinition, ...]] = {}
        inherited_static_overloads: dict[str, tuple[MethodDefinition, ...]] = {}
        if parent_name is not None:
            parent = self.get_class(parent_name)
            inherited_attributes.update(parent.attributes)
            inherited_methods.update(parent.methods)
            inherited_static_attributes.update(parent.static_attributes)
            inherited_static_methods.update(parent.static_methods)
            inherited_overloads.update(parent.method_overloads)
            inherited_static_overloads.update(parent.static_method_overloads)
        inherited_attributes.update(attributes or {})
        inherited_methods.update(methods or {})
        inherited_static_attributes.update(static_attributes or {})
        inherited_static_methods.update(static_methods or {})
        inherited_overloads.update(method_overloads or {})
        inherited_static_overloads.update(static_method_overloads or {})
        blueprint = ClassBlueprint(
            name, inherited_attributes, inherited_methods, constructor, parent_name,
            inherited_static_attributes, inherited_static_methods,
            inherited_overloads, inherited_static_overloads,
        )
        self._classes[name] = blueprint
        return blueprint

    def register_ast(self, declaration: ClassDeclaration) -> ClassBlueprint:
        """Convert a parsed C++/Java class declaration into a runtime blueprint.

        Only literal field initializers have a value during Phase 4. Non-literal
        initializers are evaluated later by the unified evaluator and begin as
        ``None`` here.
        """
        attributes = {
            field.name: self._literal_value(field.value)
            for field in declaration.attributes
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
            target.setdefault(method.name, tuple())
            target[method.name] = (*target[method.name], definition)
        constructors = declaration.constructors
        if len(constructors) > 1:
            raise ValueError(f"Class {declaration.name!r} has more than one constructor")
        constructor = (
            MethodDefinition(tuple(constructors[0].parameters), constructors[0].body, tuple(constructors[0].parameter_types))
            if constructors else None
        )
        return self.register(
            declaration.name, attributes=attributes, methods=methods,
            constructor=constructor, parent_name=declaration.parent_name,
            static_attributes={field.name: self._literal_value(field.value) for field in declaration.static_attributes},
            static_methods=static_methods,
            method_overloads=overloads,
            static_method_overloads=static_overloads,
        )

    def instantiate(self, class_name: str) -> ObjectInstance:
        """Allocate an object with a fresh copy of its class's default state."""
        blueprint = self.get_class(class_name)
        return ObjectInstance(class_name, dict(blueprint.attributes))

    def call_method(
        self,
        instance: ObjectInstance,
        method_name: str,
        arguments: Sequence[object],
        executor: MethodExecutor,
    ) -> object | None:
        """Route ``instance.method(arguments)`` and provide self/this bindings."""
        blueprint = self.get_class(instance.class_name)
        try:
            overloads = blueprint.method_overloads.get(method_name, ())
            types = tuple(_runtime_type(item) for item in arguments)
            method = next((candidate for candidate in overloads if candidate.parameter_types == types), next((candidate for candidate in overloads if len(candidate.parameters) == len(arguments)), blueprint.methods[method_name]))
        except KeyError as error:
            raise AttributeError(f"{instance.class_name} has no method {method_name!r}") from error
        if len(arguments) != len(method.parameters):
            raise TypeError(
                f"{instance.class_name}.{method_name}() expects {len(method.parameters)} argument(s), "
                f"got {len(arguments)}"
            )

        bindings: dict[str, object] = {"self": instance, "this": instance}
        bindings.update(zip(method.parameters, arguments, strict=True))
        return executor(method.body, MethodContext(instance, bindings, instance.class_name))

    def call_static_method(
        self, class_name: str, method_name: str, arguments: Sequence[object], executor: MethodExecutor,
    ) -> object | None:
        """Run an evaluator static method without requiring object construction."""
        blueprint = self.get_class(class_name)
        try:
            overloads = blueprint.static_method_overloads.get(method_name, ())
            types = tuple(_runtime_type(item) for item in arguments)
            method = next((candidate for candidate in overloads if candidate.parameter_types == types), next((candidate for candidate in overloads if len(candidate.parameters) == len(arguments)), blueprint.static_methods[method_name]))
        except KeyError as error:
            raise AttributeError(f"{class_name} has no static method {method_name!r}") from error
        if len(arguments) != len(method.parameters):
            raise TypeError(f"{class_name}.{method_name}() expects {len(method.parameters)} argument(s), got {len(arguments)}")
        instance = ObjectInstance(class_name, {})
        bindings: dict[str, object] = {"self": instance, "this": instance}
        bindings.update(zip(method.parameters, arguments, strict=True))
        return executor(method.body, MethodContext(instance, bindings, class_name))

    def get_static_attribute(self, class_name: str, name: str) -> object:
        blueprint = self.get_class(class_name)
        try:
            return blueprint.static_attributes[name]
        except KeyError as error:
            raise AttributeError(f"{class_name} has no static attribute {name!r}") from error

    def set_static_attribute(self, class_name: str, name: str, value: object) -> None:
        blueprint = self.get_class(class_name)
        if name not in blueprint.static_attributes:
            raise AttributeError(f"{class_name} has no static attribute {name!r}")
        blueprint.static_attributes[name] = value

    def call_constructor(
        self,
        instance: ObjectInstance,
        arguments: Sequence[object],
        executor: MethodExecutor,
    ) -> object | None:
        """Run the optional constructor immediately after object allocation."""
        blueprint = self.get_class(instance.class_name)
        if blueprint.parent_name is not None:
            parent = self.get_class(blueprint.parent_name)
            constructor = blueprint.constructor
            explicit_super = constructor is not None and any(
                isinstance(statement, SuperConstructorCall) for statement in constructor.body.statements
            )
            if not explicit_super:
                self._call_constructor(parent, instance, (), executor)
        return self._call_constructor(blueprint, instance, arguments, executor)

    def call_parent_constructor(
        self, instance: ObjectInstance, child_class: str, arguments: Sequence[object], executor: MethodExecutor,
    ) -> object | None:
        """Execute an explicit ``super(...)`` call from a child constructor."""
        child = self.get_class(child_class)
        if child.parent_name is None:
            raise RuntimeError(f"Class {child_class!r} has no parent constructor")
        return self._call_constructor(self.get_class(child.parent_name), instance, arguments, executor)

    def _call_constructor(
        self,
        blueprint: ClassBlueprint,
        instance: ObjectInstance,
        arguments: Sequence[object],
        executor: MethodExecutor,
    ) -> object | None:
        constructor = blueprint.constructor
        if constructor is None:
            if arguments:
                raise TypeError(f"{blueprint.name} has no constructor accepting arguments")
            return None
        if len(arguments) != len(constructor.parameters):
            raise TypeError(
                f"{blueprint.name}() expects {len(constructor.parameters)} argument(s), got {len(arguments)}"
            )
        bindings: dict[str, object] = {"self": instance, "this": instance}
        bindings.update(zip(constructor.parameters, arguments, strict=True))
        return executor(constructor.body, MethodContext(instance, bindings, blueprint.name, True))

    def get_class(self, name: str) -> ClassBlueprint:
        try:
            return self._classes[name]
        except KeyError as error:
            raise NameError(f"Class {name!r} is not registered") from error

    @staticmethod
    def _literal_value(value: object) -> object | None:
        if isinstance(value, NumberLiteral | BooleanLiteral):
            return value.value
        return None


def _runtime_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "String"
    return "unknown"
