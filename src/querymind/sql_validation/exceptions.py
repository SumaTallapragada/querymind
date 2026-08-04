"""Domain-specific exceptions for the SQL Validation Engine.

Ordinary validation findings — an unknown table, an unsupported
function, a business-rule mismatch — are never raised as exceptions;
they are reported as `ValidationIssue` data inside a `SQLValidationResult`,
so a caller always gets a complete picture even when the SQL is invalid.
These exceptions are reserved for the narrower set of failures that mean
the pipeline genuinely cannot proceed: the SQL can't be parsed at all
(caught internally by `SQLValidationEngine` and converted into a single
critical issue, never propagated to a caller under normal use — see
`querymind.sql_validation.engine`), or a required collaborator
(`MetadataRegistry`, `BusinessKnowledgeRegistry`) hasn't been loaded.
"""

from __future__ import annotations


class SQLValidationError(Exception):
    """Base class for every exception raised by `querymind.sql_validation`."""


class SQLSyntaxError(SQLValidationError):
    """Raised by `SQLParser.parse` when sqlglot cannot parse the SQL at all.

    Caught internally by `SQLValidationEngine.validate` and converted into
    the sole issue of an otherwise-empty `SQLValidationResult` — nothing
    downstream of parsing can run without an AST, so this is the one
    case where the pipeline stops immediately rather than continuing.
    """


class SchemaValidationError(SQLValidationError):
    """Raised when the Metadata Engine collaborator required for validation isn't ready.

    An engine-configuration failure (e.g. `MetadataRegistry` hasn't been
    `.load()`ed), not a per-query finding — those are reported as
    `ValidationIssue`s with code `"unknown_table"`/`"unknown_column"`/....
    """


class BusinessRuleViolationError(SQLValidationError):
    """Raised when the Business Knowledge Engine collaborator required for validation isn't ready.

    Mirrors `SchemaValidationError` for `BusinessKnowledgeRegistry` — an
    engine-configuration failure, not a per-query business-rule finding
    (those are reported as `ValidationIssue`s with code
    `"business_metric_schema_mismatch"`).
    """


class UnsupportedDialectError(SQLValidationError):
    """Reserved for a caller that wants to *reject outright* rather than report a dialect issue.

    `DialectValidator` itself always reports dialect incompatibilities as
    `ValidationIssue`s (per "the caller receives a complete picture of
    all detected issues") — this type is not raised by the default
    pipeline, but is part of the package's public exception surface for
    a future strict-mode caller to use.
    """
