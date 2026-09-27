# Polyglot Compiler Implementation Status

**Audited:** 26 September 2026  
**Project:** `E:\polyglot_compiler`  
**Runtime model:** one shared lexer/parser/AST/evaluator for a deliberately small subset of C++, Java, and Python, plus an optional native-toolchain runner.

## Executive summary

The project is no longer only a Phase 1 lexer. It currently contains:

- three language front ends;
- a shared recursive-descent parser and AST;
- scoped variables, functions, returns, expressions, arrays/lists, and control flow;
- C++/Java classes, constructors, objects, inheritance, method dispatch, and Java `super(...)` forwarding;
- evaluator-mode input, strings, list operations, simplified exceptions, and sandboxed text files;
- structural validation for complete source files;
- a native runner for real `g++`, `javac/java`, and Python execution;
- static type diagnostics, trace mode, REPL, linter/formatter, and a small bytecode VM;
- safe Python `math` imports, single-clause comprehensions, tuples, and `with open` blocks;
- C++ base-constructor initializer forwarding and Java static fields/methods;
- C++ reference binding, type-aware method overload selection, and bytecode counted loops;
- bytecode function calls/returns plus C++/Java object construction, fields,
  constructors, inheritance, overriding, and Java static members;
- debugger step/event/source-line breakpoints/watch controls and bytecode profiling;
- command-oriented CLI aliases backed by a central frontend registry;
- installable package metadata and a `polyglot` console command (`main:main`);
- bytecode constant folding, redundant/unreachable instruction removal,
  control-flow relocation, profiling, and readable disassembly;
- configurable evaluator/bytecode recursion limits with function-aware overflow errors;
- evaluator and bytecode call-depth protection, including recursive methods;
- installable packaging, TOML project defaults, and a manifest-driven program suite;
- evaluator/bytecode/optimized-bytecode benchmark comparisons with JSON/CSV export;
- structured runtime diagnostic codes and recursive call-chain errors;
- recoverable multi-error parser diagnostics with source-line caret reports;
- actionable parser hints for common missing tokens and incomplete expressions;
- 132 automated tests, including automatic front-end parsing for each example file.

This is a working educational interpreter/evaluator, not yet a complete C++ compiler, Java compiler, or Python implementation.

## Repository map

| Area | Files | Responsibility |
|---|---|---|
| CLI | `main.py`, `pyproject.toml` | Select language, evaluator/native/bytecode engine, token/AST display, validation, diagnostics, and installable `polyglot` entry point |
| AST | `core/ast_nodes.py` | Program, expressions, declarations, functions, loops, classes, switch/try nodes |
| Parser | `core/parser.py` | Shared recursive-descent parser plus recoverable multi-error reporting |
| Scope | `core/symbol_table.py` | Nested scopes, function definitions, arguments, return propagation |
| OOP | `core/oop.py` | Class blueprints, instances, constructors, inheritance, method dispatch |
| Validation | `core/validator.py` | Complete-file structure and evaluator-compatibility diagnostics |
| Lexers | `frontends/*_lexer.py`, `frontends/brace_lexer.py` | C++/Java tokens, Python indentation tokens, source locations |
| Front-end adapters | `frontends/*_parser.py`, `frontends/registry.py` | Language-specific parser configuration and centralized frontend registration |
| Bytecode | `core/bytecode.py` | Compiles and executes functions, control flow, and object-oriented subset code |
| Debugger | `runtime/debugger.py` | Event/source-line breaks, watches, stepping, and bytecode profiling hooks |
| Benchmarking | `runtime/benchmark.py`, `benchmarks/` | Backend comparison, correctness checks, timing, instruction counts, JSON/CSV reports |
| Runtime errors | `runtime/errors.py` | Stable error codes and call-chain diagnostics |
| Evaluator | `runtime/evaluator.py` | Executes the shared AST with safety limits and built-ins |
| Native runner | `runtime/native_runner.py` | Runs real C++/Java/Python toolchains with timeout handling |
| Tests | `tests/` | Lexer, parser, evaluator, OOP, validator, CLI, native-runner tests |
| Examples | `examples/` | Feature demonstrations and complete-file validation examples |

## Language capability matrix

### Common evaluator features (all three tracks)

Implemented and covered by tests:

- integer/float/boolean/string literals and identifiers;
- arithmetic, comparisons, equality, logical operators, unary operators, parentheses;
- assignment and compound assignment (`+=`, `-=`, `*=`, `/=`, `%=`);
- variable declarations and scoped symbol lookup;
- `if`/`else if`/`else`, `while`, counted `for`, `break`, and `continue`;
- arrays/lists, brace or bracket literals, indexing, indexed assignment, nested arrays;
- functions with parameters, local scope, return values, and arity checks;
- `print`, `input`/portable input helpers, numeric/string conversion, `len`;
- twenty string operations and ten list/array operations;
- simplified `try/catch` or `try/except`;
- sandboxed UTF-8 text files under the project's `data/` directory;
- loop iteration limits to prevent accidental infinite evaluator loops.

### C++ subset

Implemented:

- complete-file requirement in evaluator/check mode: first meaningful line must be `#include`, and an `int main(...)` block is required;
- evaluator accepts and ignores ordinary `#include` lines (it does not link those headers);
- typed declarations such as `int`, `float`, `bool`, `string`, and arrays;
- C++ brace blocks, semicolon-terminated statements, `cin >> variable`, postfix `++`/`--`;
- counted `for`, collection `for (int value : values)`, and `do ... while`;
- `switch`/`case`/`default` with brace-language fall-through;
- classes, one constructor, object state, methods, C++-style inheritance (`class Child : Parent`);
- array initializers such as `int items[] = {1, 2, 3};` and nested array literals.

Not implemented by the evaluator: real `std::cout`, `std::cin`, `std::vector`, templates other than the portable `vector<T>` facade, pointers, preprocessing/macros beyond `#include`, operator overloading, and the complete C++ standard library. Use `--engine native` for those. C++ reference parameters are supported in evaluator mode.

### Java subset

Implemented:

- complete-file requirement: one public class matching the `.java` filename and `public static void main(String[] args)`;
- Java wrapper normalization for package/import/modifier syntax used by the supported subset;
- `int`, `double`, `boolean`, `String`, arrays, `new`, methods, constructors, and object fields;
- Java collection-style `for`, `do ... while`, `switch`, classes, inheritance (`extends`), overriding, constructor `super(arguments)`, and static fields/methods;
- lightweight `Scanner` support for `nextInt`, `nextDouble`, and `nextLine`;
- Java/C++-style string and list method aliases.
- evaluator output aliases for `System.out.print(...)` and `System.out.println(...)`.
- evaluator collection facades for `ArrayList<T>`, `HashMap<K, V>`, and `HashSet<T>`.

Not implemented by the evaluator: the rest of the Java class library, generics beyond skipped collection type annotations, interfaces, annotations, threads, checked-exception semantics, access-control enforcement, and full package/import semantics. Method overloading is supported by declared parameter types, then arity. Use `--engine native` for real Java.

### Python subset

Implemented:

- indentation-sensitive lexer and parser;
- assignments, expressions, functions, `if`/`elif`/`else`, `while`, `for ... in range(...)`, and `for ... in values`;
- `break`, `continue`, `match`/`case`, nested lists, indexing, string/list helpers;
- `input`, conversions, simplified `try`/`except`, sandboxed files, `None`, dictionaries, and sets;
- Python-style method aliases such as `upper`, `find`, `append`, `index`, and `len`.

Not implemented by the evaluator: imports other than safe `math`, comprehensions with conditions/multiple clauses, generators, decorators, async features, modules, most built-in functions, and full Python object/protocol behavior. The native engine runs normal Python with the installed interpreter.

## Complete-file rules and example interpretation

`--check` and evaluator mode intentionally distinguish **structure** from **evaluator compatibility**:

- C++: `#include` and `int main(...)` are required.
- Java: the public class must match the filename and contain the standard main signature.
- Python: normal Python syntax is checked; no artificial `main` wrapper is required.

Many feature examples are snippets, not complete C++/Java applications. Therefore a small file such as `examples/arrays_cpp.cpp` can be evaluator-compatible as a snippet but fail the complete-file structure check. The complete wrapper examples are `examples/samarth_cpp.cpp`, `examples/matrix_cpp.cpp`, `examples/matrix_java.java`, `examples/complete_java_main.java`, and `examples/complete_inheritance_java.java`.

## Verified test status

Command used:

```powershell
Set-Location E:\polyglot_compiler
& 'C:\Users\Samarth\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

Result after Phases 17–29: recursion safety, packaging/configuration, test
fixtures, benchmarking, call-chain diagnostics, bytecode optimization, CLI routing,
parser recovery, and actionable syntax hints:

```text
Ran 132 tests
OK
```

The tests cover lexing, source locations, parser precedence, arrays, functions, scopes, loops, input, OOP, constructors, inheritance, strings, lists, exceptions, file sandboxing, validation, CLI errors, native-runner error handling, and the manifest-driven valid/invalid program fixture suite. Run the latter with `python main.py --test-all`.

## Known gaps to fix before calling it production-ready

1. **Type system:** values are mostly Python objects; static checks are conservative and do not yet enforce every implicit-conversion policy or compile-time rule.
2. **Inheritance constructors:** single-level Java `super(...)` and C++ base-initializer forwarding work; multi-level constructor policy and multiple constructors per class remain limited.
4. **Language coverage:** no complete grammar, standard library, modules/imports, generics/templates, pointers, or robust access modifiers.
5. **Diagnostics:** multi-error parser recovery and common missing-token hints
   are available through normal errors and `--syntax-report`; richer expected-
   token lists and deeper nested-construct recovery can still be improved.
6. **Performance:** bytecode covers expressions, control flow, functions, and objects and now has conservative optimization, disassembly, profiling, benchmark workloads, and CSV/JSON reports; repeatable multi-run statistics and native-code generation remain pending.
7. **Interactive tooling:** REPL, debugger, type diagnostics, linter, and safe formatter are present; there is no language-server integration or source maps.
8. **Native isolation:** native execution depends on external `g++`, `javac/java`, and Python installations; it is a toolchain wrapper, not a portable compiler backend.

## Recommended development order

### Month 1 — correctness foundation

Align validator rules with actual evaluator behavior, add a formal type/value layer, improve diagnostics, add regression tests for every example, and define a documented language-subset specification.

### Month 2 — core language semantics

Add `null`/`None`, richer booleans, type checking, function return-type checks, better array bounds diagnostics, explicit scope rules, and controlled recursion/function-call depth.

### Month 3 — C++ subset expansion

Implement evaluator-native `cout`/`cerr` aliases, a safe `vector`-like collection, more declarations, `const`, richer `switch`, and selected references. Keep templates, pointers, and the full standard library delegated to native mode.

### Month 4 — Java subset expansion

Add typed exception names, broader constructor chaining, overload resolution, static members, access checks, and a larger Java collection subset.

### Month 5 — Python subset expansion

Add dictionaries, sets, comprehensions, imports from an allow-list, `with` for safe files, richer built-ins, and more faithful Python truthiness/iteration behavior.

### Month 6 — tooling and release quality

Add bytecode optimization and profiling, then add a benchmark suite, documentation site, packaging, CI, security review, and a stable versioned subset specification.

## Six-month projection

At the current development speed, six months can realistically produce a strong educational multi-language subset, not three industrial-strength language implementations. A reasonable target is:

- 20–40 additional well-tested feature increments;
- validator and evaluator behavior kept synchronized;
- substantially better diagnostics and documentation;
- a small typed runtime plus safer object/collection semantics;
- selected C++/Java/Python library facades;
- optional bytecode/IR execution for measurable speedups;
- CI and repeatable native/evaluator regression runs;
- approximately 150–250 focused automated tests, depending on feature size.

The scope must remain explicit. Supporting every feature of C++, Java, and Python in six months would require a full compiler team and is not a realistic extension of this tree-walk architecture. The best outcome is a reliable, teachable “Polyglot Subset” with native mode available whenever full language behavior is required.

## Useful commands

```powershell
Set-Location E:\polyglot_compiler

# Evaluator mode
python main.py --lang cpp examples\samarth_cpp.cpp
python main.py --lang java examples\complete_java_main.java
python main.py --lang python examples\python_demo.py

# Inspect the pipeline
python main.py --lang cpp --tokens examples\samarth_cpp.cpp
python main.py --lang cpp --ast examples\samarth_cpp.cpp

# Validate complete-file structure without executing
python main.py --lang cpp --check examples\samarth_cpp.cpp
python main.py --lang java --check examples\complete_java_main.java
python main.py --lang python --check examples\validation\full_python.py

# Use the real language toolchain
python main.py --lang cpp --engine native examples\validation\complete.cpp
python main.py --lang java --engine native examples\validation\Main.java
python main.py --lang python --engine native examples\validation\full_python.py
```
