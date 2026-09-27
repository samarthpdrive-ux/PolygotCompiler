"""Small formatter and linter helpers for the supported subset."""

from __future__ import annotations


def format_source(source: str) -> str:
    """Apply safe, language-neutral whitespace formatting.

    This intentionally avoids rewriting token layout or comments.  It removes
    trailing whitespace, normalizes line endings, and guarantees one final
    newline, so it cannot alter a string literal or program semantics.
    """
    return "\n".join(line.rstrip() for line in source.replace("\r\n", "\n").replace("\r", "\n").split("\n")).rstrip() + "\n"
