# Polyglot Compiler Framework — Phases 1–5

For the current audited feature inventory, verified test result, known gaps,
and six-month roadmap, see [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

## Compiler tooling

The CLI provides static checks, tracing, a small REPL, safe formatting, linting,
and a stack-bytecode mode for expressions, control flow, functions, and the
shared C++/Java object subset:

```powershell
python main.py --lang cpp --type-check examples\samarth_cpp.cpp
python main.py --lang cpp --strict-types path\to\program.cpp
python main.py --lang python --trace examples\python_demo.py
python main.py --lang python --lint examples\advanced_python.py
python main.py --lang python --format examples\advanced_python.py
python main.py --lang python --repl
python main.py --lang python --engine bytecode examples\bytecode_python.py
python main.py --lang python --engine bytecode examples\bytecode_function_python.py
python main.py --lang python --step examples\advanced_python.py
python main.py --lang python --trace --break 3 --watch total examples\bytecode_for_python.py
python main.py --lang python --break-line 2 --watch total examples\bytecode_for_python.py
python main.py --lang cpp --engine bytecode --profile examples\bytecode_classes_cpp.cpp
python main.py compile --lang python --optimize --disassemble --profile examples\bytecode_optimized_python.py
python main.py run --lang python --max-call-depth 200 examples\recursive_factorial_python.py
python main.py --test-all
python main.py test --lang cpp
python main.py benchmark --lang python --benchmark-export benchmarks\result.json benchmarks\loop_python.py

# Equivalent command-oriented interface
python main.py run --lang python examples\python_demo.py
python main.py check --lang cpp examples\validation\complete.cpp
python main.py compile --lang python examples\bytecode_function_python.py
python main.py debug --lang python --break-line 2 examples\bytecode_for_python.py
python main.py format --lang python examples\advanced_python.py
python main.py lint --lang python examples\advanced_python.py
```

`--type-check` reports definite type mismatches; `--strict-types` blocks
evaluator execution on those errors. `--format` deliberately makes only safe
whitespace changes. Bytecode mode supports declarations, assignments,
arithmetic/comparisons, `print`, `if`, `while`, counted `for` loops, function
declarations/calls/returns, C++/Java classes, fields, constructors, inherited
methods, overriding, and Java static fields/methods. Trace debugging accepts
`--step`, event breakpoints with `--break 3,8`, source-line breakpoints with
`--break-line 2,8`, and watched assignments with `--watch total,count`.
`--profile` reports bytecode instruction counts and elapsed time.
`--optimize` enables literal constant folding, safe expression-result cleanup,
no-op jump removal, and unreachable-code removal after `return`; jump targets
are relocated during each pass. `--disassemble` prints numbered bytecode for
the main block, functions, classes, constructors, and methods. Compare
`--profile` with and without `--optimize` using
`examples/bytecode_optimized_python.py`.
Evaluator and bytecode calls also enforce a configurable recursion limit with
`--max-call-depth` (default `200`). A recursive overflow reports the function
name instead of exposing a host-language recursion traceback. See
`examples/recursive_factorial_python.py`.
The command-oriented forms are aliases over the same pipeline, so existing
flag-based commands remain supported. Language frontends are registered in
`frontends/registry.py`; adding a future language only requires a lexer,
parser, registry entry, and tests rather than new CLI execution branches.

## Program fixture suite

`tests/programs/manifest.json` defines end-to-end valid and invalid programs
for each supported language. Each case declares its language, source path,
expected exit status, and required stdout/stderr fragments. Run every fixture
through the public CLI with `python main.py --test-all`, or filter one language
with `python main.py test --lang java`. This is separate from the Python unit
test suite and is designed for repeatable demonstrations and regression tests.

## Benchmarks and runtime diagnostics

`benchmark` runs one program through evaluator mode, bytecode mode, and
optimized bytecode mode. It checks that output and global values agree, then
prints elapsed time and bytecode instruction counts. Export a report as JSON
or CSV for the diploma evaluation.

```powershell
polyglot benchmark --lang python benchmarks\loop_python.py
polyglot benchmark --lang python --benchmark-export benchmarks\report.json benchmarks\recursion_python.py
```

Runtime failures now use stable diagnostic codes, for example
`Runtime error [CALL_DEPTH]`. Recursive overflow messages include the active
function/method call chain, which makes recursion and method errors easier to
diagnose without exposing a Python traceback.

## Installation and `polyglot` command

The project has no runtime dependencies beyond Python's standard library. From
the project root, install it in editable mode while developing:

```powershell
python -m pip install --editable .
```

This registers the `polyglot` console command and uses the same CLI pipeline as
`python main.py`:

```powershell
polyglot run --lang python examples\python_demo.py
polyglot check --lang cpp examples\validation\complete.cpp
polyglot compile --lang python --optimize examples\bytecode_optimized_python.py
```

## Project configuration

Use an optional `polyglot.toml` in the current directory, or pass an explicit
path with `--config`. CLI values always override configuration values.

```toml
[polyglot]
language = "python"
engine = "bytecode"
max_call_depth = 200
max_loop_iterations = 100000
```

```powershell
polyglot --config path\to\polyglot.toml examples\program.py
```

To verify package metadata without installing it, run:

```powershell
python -m unittest tests.test_packaging -v
```

Phase 1 tokenizes small C++, Python, and Java subsets. Phase 2 converts those
token streams into ASTs for assignments, arithmetic expressions with operator
precedence, `if`/`else`, and `while` statements. Phase 3 adds a hierarchical
symbol table for local/global variables and function-call parameter scopes.
Phase 4 adds C++/Java class declarations, object construction, per-instance
attributes, and method-dispatch bindings. Phase 5 completes the AST evaluator
and command-line pipeline for all three supported language subsets.

Example Phase 3 usage:

```python
symbols = SymbolTable()
symbols.define("global_value", 10)
with symbols.scope("function:demo"):
    symbols.define("local_value", 20)  # Removed when the scope exits.
```

Run a program from the project directory:

```powershell
python main.py --lang python path\to\program.py
```

Use `--tokens` or `--ast` to inspect earlier pipeline stages.

### Mandatory complete-file checks for C++ and Java

Evaluator and check mode both require complete C++ and Java source files. C++
must begin (apart from comments/blank lines) with `#include` and contain
`int main(...) { ... }`. Java must contain exactly one public class whose name
matches the `.java` filename and a `public static void main(String[] args)`
entry point. Functions are declared normally, but execution begins from `main`.

```powershell
python main.py --lang cpp --check examples\validation\complete.cpp
python main.py --lang java --check examples\validation\Main.java
```

The teaching evaluator accepts these wrappers, then evaluates their supported
bodies: it ignores C++ headers and Java modifiers/import lines, and invokes the
declared `main`. Its supported output aliases are `cout << value << endl;` and
`System.out.println(value);`; use `--engine native` for `std::cout` and the
full external-header/package libraries.

## Collection loops, do-while, and inheritance

In addition to indexed `for` loops, C++/Java accept collection loops such as
`for (int value : values)`, while Python accepts `for value in values:`.
C++/Java also support `do { ... } while (condition);`. Classes can inherit
fields and methods with `class Student : Person` in C++ or
`class Student extends Person` in Java; child methods override parent methods.
Inside a method, declared fields may be accessed as either `name` or
`this.name`. See `examples/foreach_cpp.cpp`, `examples/do_while_cpp.cpp`,
`examples/inheritance_cpp.cpp`, and `examples/complete_inheritance_java.java`.

To check a complete real-language file without trying to execute it through the
lightweight evaluator, use structural validation:

```powershell
python main.py --lang cpp --check path\to\program.cpp
python main.py --lang java --check path\to\Main.java
python main.py --lang python --check path\to\program.py
```

### Complete C++ wrapper in evaluator mode

The C++ evaluator accepts `#include <...>` directives and ignores them because
it does not link real C++ headers. It also automatically calls a parsed
zero-argument `int main()`. Thus this evaluator-compatible form is valid:

```cpp
#include <iostream>
int main() {
    int items[] = {1, 2, 3, 4, 5};
    print(items[0]);
    return 0;
}
```

Use the evaluator's `print(...)`, `cin`, `string`, and supported collection
methods within this subset. For true `std::cout`, `std::vector`, and external
headers, use `--engine native`; the native compiler handles full C++ syntax.

The report keeps two statuses separate: **Structure** checks complete-file
requirements such as C++ `#include`/`main`, Java class/main/file-name rules,
delimiter balance, and Python syntax. **Evaluator compatibility** states
whether the source uses features outside this project's implemented subset.

Try the full-format validation examples in `examples/validation/` with the
same `--check` command. They intentionally use real language features that
are structurally correct but outside the lightweight evaluator's subset.

## Native execution for complete programs

Use the native engine when you want the real language toolchain, rather than
the teaching evaluator. It supports interactive input because it connects the
program directly to your terminal.

```powershell
python main.py --lang cpp --engine native path\to\program.cpp
python main.py --lang java --engine native path\to\Main.java
python main.py --lang python --engine native path\to\program.py
```

The required tools must be installed and available on `PATH`: `g++` for C++,
`javac` and `java` for Java, and Python for Python. Use `--timeout 60` if a
normal compile or program execution needs more than the default 30 seconds.

Check whether a complete native file compiles, without running it:

```powershell
python main.py --lang cpp --engine native --compile-only path\to\program.cpp
python main.py --lang java --engine native --compile-only path\to\Main.java
python main.py --lang python --engine native --compile-only path\to\program.py
```

Compiler and syntax errors are displayed with their native line-number
diagnostics, such as `g++` or `javac` error messages.

Use a real source-file path in place of the examples above. For example, the
included files are `examples\validation\complete.cpp`,
`examples\validation\Main.java`, and `examples\python_demo.py`.

Runnable subset examples are in `examples/`:

```powershell
python main.py --lang python examples\python_demo.py
python main.py --lang cpp examples\cpp_demo.cpp
python main.py --lang java examples\java_demo.java
```

## Interactive input in evaluator mode

The teaching evaluator now supports strings and terminal input in each source
track. These are intentionally small, consistent subsets rather than complete
standard-library implementations:

```text
# Python
name = input("Name: ")
age = int(input("Age: "))

// C++ subset (declare a type before using cin)
string name; int age; cin >> name; cin >> age;

// Java subset (no import needed in the teaching evaluator)
Scanner scanner = new Scanner(System.in);
String name = scanner.nextLine();
int age = scanner.nextInt();
```

Java also supports `scanner.nextDouble()`. The generic evaluator built-ins
`readInt()`, `readFloat()`, and `readLine()` are available in all three tracks.
Run the included interactive evaluator examples with `input_python.py`,
`input_cpp.cpp`, or `input_java.java`.

## Counted `for` loops in evaluator mode

The evaluator supports counted loops in the following forms:

```text
for (int number = 1; number < 6; number = number + 1) { ... }  // C++ / Java
for number in range(1, 6):                                      # Python
    ...
```

Python `range(stop)`, `range(start, stop)`, and `range(start, stop, step)`
are supported when `step` is a positive integer. See `examples/for_cpp.cpp`,
`examples/for_java.java`, and `examples/for_python.py`.

## Arrays and lists in evaluator mode

Use indexed values with `values[index]` in expressions or assignments. The
supported declaration syntax is `int marks[3] = {70, 82, 91};` for C++,
`int[] marks = {70, 82, 91};` for Java, and `marks = [70, 82, 91]` for
Python. See the `examples/arrays_*` programs for an indexed loop and update.

## Parameterized constructors in evaluator mode

Java and C++ classes can define one constructor whose name matches the class,
then instantiate with arguments: `Student student = new Student("Samarth", 24);`.
Use `this.attribute` inside constructors and methods. See
`examples/constructors_java.java` and `examples/constructors_cpp.cpp`.

## `break` and `continue`

All three evaluator tracks support `break;` / `continue;` in C++ and Java,
and `break` / `continue` in Python. They affect the innermost `while` or
`for` loop. See the `examples/break_continue_*` programs.

## Compound assignments and increments

All evaluator tracks support `+=`, `-=`, `*=`, `/=`, and `%=`. C++ and Java
also support postfix `++` and `--`. See `examples/compound_cpp.cpp`,
`examples/compound_java.java`, and `examples/compound_python.py`.

## Logical and nested conditions

Use `&&`, `||`, and `!` in C++/Java; use `and`, `or`, and `not` in Python.
Parentheses can group nested conditions. See `examples/logical_conditions_cpp.cpp`,
`examples/logical_conditions_java.java`, and `examples/logical_conditions_python.py`.

## Twenty string operations

The evaluator supports these operations: `length` / `len`, upper case, lower
case, trim, contains, starts-with, ends-with, replace, substring, character at
an index, first index, last index, empty check, equality check, split, repeat,
reverse, capitalize, title case, and count. Java/C++ use names such as
`text.toUpperCase()` and `text.indexOf("x")`; Python aliases such as
`text.upper()` and `text.find("x")` also work. The evaluator provides
`substring`, `charAt`, `isEmpty`, `equals`, `repeat`, and `reverse` as portable
subset helpers in the Python track. See `examples/string_methods_cpp.cpp`,
`examples/string_methods_java.java`, and `examples/string_methods_python.py`.

## Ten list and array operations

The evaluator supports append/add, remove, pop, clear, length/size/`len`,
contains, index-of, reverse, sort, and get/set. Java/C++ aliases include
`add`, `size`, and `indexOf`; Python aliases include `append`, `index`, and
`len(values)`. The portable subset provides `contains`, `get`, `set`, and
`length` for Python lists. See `examples/list_methods_cpp.cpp`,
`examples/list_methods_java.java`, and `examples/list_methods_python.py`.

## Multi-branch conditions

Use `else if` in C++/Java and `elif` in Python for any number of conditional
branches, followed by an optional final `else`. See `examples/else_if_cpp.cpp`,
`examples/else_if_java.java`, and `examples/elif_python.py`.

## Switch and match statements

The C++/Java subset supports `switch`, `case`, `default`, and `break`; standard
fall-through applies when a case has no `break`. Python supports `match` and
`case`, including `case _` as the default branch, without fall-through. See
`examples/switch_cpp.cpp`, `examples/switch_java.java`, and `examples/match_python.py`.

## Exception handling

The evaluator supports one simplified handler: `try { ... } catch { ... }` in
C++/Java and `try: ... except: ...` in Python. It catches ordinary evaluator
errors, including invalid numeric conversions, undefined variables, invalid
indexes, unsupported method calls, and division by zero. See
`examples/try_catch_cpp.cpp`, `examples/try_catch_java.java`, and
`examples/try_except_python.py`.

## Sandboxed text files

All tracks support `open("name.txt", "r" | "w" | "a")`, plus `write`, `read`,
`readLine`, `flush`, and `close`. Files are restricted to this project's
`data/` folder; absolute paths and `..` escapes are rejected. Use
`fileExists("name.txt")` to check for a sandboxed file. See `examples/file_cpp.cpp`,
`examples/file_java.java`, and `examples/file_python.py`.

## Maps, sets, and collection facades

Python supports dictionary and set literals, dictionary indexing, and portable
map/set methods. The evaluator also provides lightweight collection facades:
`ArrayList<T>` / `HashMap<K, V>` / `HashSet<T>` in Java and `vector<T>` in C++.
They support only the documented shared list, map, and set methods; they are
not replacements for the real standard libraries. See `examples/collections_cpp.cpp`,
`examples/collections_java.java`, and `examples/collections_python.py`.

Java child constructors may call `super(arguments);` to forward arguments to a
parent constructor. See `examples/super_java.java`.

## References, overloads, and bytecode objects

C++ reference parameters bind to caller storage in evaluator mode, so
`void increment(int& value)` can update its argument. Java methods and global
functions select overloads by declared parameter type when available, then
fall back to arity. Bytecode mode supports counted `range(...)` loops, object
creation, constructors, instance fields, method calls, inheritance/overrides,
and Java static fields/methods. See `examples/reference_cpp.cpp`,
`examples/overload_java.java`, `examples/bytecode_for_python.py`, and
`examples/bytecode_classes_cpp.cpp`.

## Additional Python and C++ subset features

Python now supports tuples, list comprehensions with one `for` clause,
`import math` (only `sqrt`, `floor`, `ceil`, `pow`, and `abs`), and safe
`with open(...) as name:` blocks that remain inside `data/`. C++ child
constructors can forward parent arguments using `Child(args) : Parent(args) {}`.
See `examples/advanced_python.py` and `examples/base_constructor_cpp.cpp`.

## Java static subset

The evaluator supports Java `static` fields and `static` methods, including
calls such as `Counter.add(3)` and member access such as `Counter.total`.
Static overload resolution and full Java access control remain native-engine
features. See `examples/static_java.java`.

## Multi-error syntax reports

Normal execution stops at the first syntax error. To inspect a work-in-progress
file and collect independent parser errors in a single pass, use
`--syntax-report`. It displays each source line with a caret and returns a
non-zero exit status when any error is found:

```powershell
python main.py --lang cpp --syntax-report tests\programs\invalid\multiple_cpp_errors.cpp
python main.py --lang python --syntax-report tests\programs\invalid\multiple_python_errors.py
```

Recovery is deliberately diagnostic-only: it does not execute the partial AST,
and a malformed nested construct can still hide errors inside that construct.
Common diagnostics also include a `Hint:` line for missing semicolons, colons,
closing delimiters, variable names, and expression values.

Run the test suite from this directory:

```powershell
& 'C:\Users\Samarth\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```
