"""Logging and progress output helpers."""

from __future__ import annotations

import time


def log(msg: str) -> None:
    """Print a message with immediate flush."""
    print(msg, flush=True)


def banner(msg: str) -> None:
    """Print a prominent section banner."""
    log("\n" + "=" * 72)
    log(msg)
    log("=" * 72)


class StepTimer:
    """Context manager that logs elapsed time for a labeled step."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.t0 = 0.0

    def __enter__(self) -> StepTimer:
        self.t0 = time.perf_counter()
        log(f"[..] {self.label}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        dt = time.perf_counter() - self.t0
        if exc is None:
            log(f"[OK] {self.label} ({dt:.2f}s)")
        else:
            log(f"[!!] {self.label} failed after {dt:.2f}s")
