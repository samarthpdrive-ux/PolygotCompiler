"""Central registry for language frontends.

Adding a language now requires one registry entry instead of editing CLI
dispatch logic in several places. A frontend owns lexing and parsing while
the runtime/backend remains language-neutral.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .cpp_lexer import lex_cpp
from .cpp_parser import parse_cpp
from .cpp_parser import parse_cpp_recovering
from .java_lexer import lex_java
from .java_parser import parse_java
from .java_parser import parse_java_recovering
from .python_lexer import lex_python
from .python_parser import parse_python
from .python_parser import parse_python_recovering


@dataclass(frozen=True, slots=True)
class Frontend:
    name: str
    lexer: Callable[[str], list]
    parser: Callable[[list], object]
    recovery_parser: Callable[[list], tuple[object, tuple[object, ...]]]

    def parse(self, source: str) -> tuple[list, object]:
        tokens = self.lexer(source)
        return tokens, self.parser(tokens)


FRONTENDS: dict[str, Frontend] = {
    "cpp": Frontend("cpp", lex_cpp, parse_cpp, parse_cpp_recovering),
    "java": Frontend("java", lex_java, parse_java, parse_java_recovering),
    "python": Frontend("python", lex_python, parse_python, parse_python_recovering),
}


def get_frontend(language: str) -> Frontend:
    """Return a registered frontend with a useful error for unknown names."""
    try:
        return FRONTENDS[language]
    except KeyError as error:
        available = ", ".join(sorted(FRONTENDS))
        raise ValueError(f"Unknown language {language!r}; available frontends: {available}") from error
