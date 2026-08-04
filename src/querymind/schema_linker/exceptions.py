"""Domain-specific exceptions for the Semantic Schema Linker.

Genuine error conditions only — a business concept the linker can't
confidently map to a schema object is *not* one of these. That outcome
is represented as data (an `Ambiguity` entry on `LinkedQueryContext`),
never as an exception, so a caller can inspect and react to it instead
of catching around a control-flow exception for an entirely ordinary
result.
"""

from __future__ import annotations


class SchemaLinkerError(Exception):
    """Base class for every exception raised by `querymind.schema_linker`."""


class EmptyRegistryError(SchemaLinkerError):
    """Raised when linking is attempted against a `MetadataRegistry` with no loaded tables."""

    def __init__(self) -> None:
        super().__init__(
            "MetadataRegistry has no tables loaded. Call registry.load() before linking."
        )
