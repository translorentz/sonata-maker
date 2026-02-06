"""Custom exceptions for the sonata generation pipeline."""

from __future__ import annotations


class SonataGenerationError(RuntimeError):
    """Raised when any step of the sonata generation pipeline fails."""
