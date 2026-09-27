"""Token data type shared by all language front ends."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Token:
    """A unit of source code with its type, value, and original position."""

    type: str
    value: int | float | str
    line: int
    column: int
