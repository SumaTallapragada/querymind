"""Domain-specific exceptions for the SQL Generation Engine."""

from __future__ import annotations


class SQLGenerationError(Exception):
    """Base class for every exception raised by `querymind.sql_generation`."""


class SQLExtractionError(SQLGenerationError):
    """Raised when no usable SQL text could be extracted from an LLM response.

    Never raised for SQL that is present but *wrong* (missing a table,
    syntactically broken, ...) — this package does not validate SQL, so
    it has no way to know that and no business judging it. Reserved for
    the narrower case of finding nothing that looks like SQL text at all.
    """
