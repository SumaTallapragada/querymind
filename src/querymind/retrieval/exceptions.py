"""Domain-specific exceptions for the Knowledge Retrieval Engine."""

from __future__ import annotations


class RetrievalError(Exception):
    """Base class for every exception raised by `querymind.retrieval`."""


class InvalidTopKError(RetrievalError):
    """Raised when `top_k` is not a positive integer."""

    def __init__(self, top_k: int) -> None:
        self.top_k = top_k
        super().__init__(f"top_k must be a positive integer, got {top_k!r}.")
