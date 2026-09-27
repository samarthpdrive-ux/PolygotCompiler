"""Structured runtime errors shared by evaluator and bytecode execution."""

from __future__ import annotations


class CompilerRuntimeError(RuntimeError):
    """Base error with a stable code for CLI tools and automated reports."""

    code = "RUNTIME"


class CallDepthExceeded(CompilerRuntimeError):
    """Raised before unbounded recursion can reach the host Python limit."""

    code = "CALL_DEPTH"

    def __init__(self, limit: int, call_chain: list[str]) -> None:
        self.limit = limit
        self.call_chain = tuple(call_chain)
        chain = " -> ".join(self.call_chain) if self.call_chain else "<entry>"
        super().__init__(f"Maximum call depth ({limit}) exceeded. Call chain: {chain}")


def format_runtime_error(error: BaseException) -> str:
    """Produce a stable diagnostic without exposing implementation tracebacks."""
    code = getattr(error, "code", "RUNTIME")
    return f"Runtime error [{code}]: {error}"
