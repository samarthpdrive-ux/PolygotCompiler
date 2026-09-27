"""Non-invasive trace debugger controls for evaluator and bytecode runs."""

from __future__ import annotations

import re


class TraceDebugger:
    """Track event numbers, optional breakpoints, and watched assignments."""

    def __init__(self, *, breakpoints: set[int] | None = None, line_breakpoints: set[int] | None = None, watches: set[str] | None = None, step: bool = False, trace_all: bool = False, output=print) -> None:
        self.breakpoints = breakpoints or set()
        self.line_breakpoints = line_breakpoints or set()
        self.watches = watches or set()
        self.step = step
        self.trace_all = trace_all
        self.output = output
        self.events = 0

    def __call__(self, message: str) -> None:
        self.events += 1
        hit_breakpoint = self.events in self.breakpoints
        line_match = re.search(r"\bat line (\d+)\b", message)
        hit_line_breakpoint = bool(line_match and int(line_match.group(1)) in self.line_breakpoints)
        watched = any(message.startswith(f"{name} =") for name in self.watches)
        if self.step or self.trace_all or hit_breakpoint or hit_line_breakpoint or watched:
            prefix = "BREAK" if hit_breakpoint or hit_line_breakpoint else "STEP" if self.step or self.trace_all else "WATCH"
            self.output(f"{prefix} [{self.events}] {message}")
