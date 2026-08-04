"""The ten independent validators, plus the `Validator` protocol they all implement.

Every validator has exactly one responsibility, reads only the
`querymind.sql_validation.parser.ParsedSQL` it's given (never another
validator's output), and never modifies the AST or the underlying SQL
text. A validator that needs a QueryMind collaborator (the Metadata
Engine, the Relationship Graph, the Business Knowledge Engine) receives
it via constructor injection — never by reaching into another validator.
"""

from __future__ import annotations

from typing import Protocol

from querymind.sql_validation.models import ValidationIssue
from querymind.sql_validation.parser import ParsedSQL
from querymind.sql_validation.validators.aggregates import AggregateValidator
from querymind.sql_validation.validators.aliases import AliasValidator
from querymind.sql_validation.validators.business_rules import BusinessRuleValidator
from querymind.sql_validation.validators.column import ColumnValidator
from querymind.sql_validation.validators.dialect import DialectValidator
from querymind.sql_validation.validators.functions import FunctionValidator
from querymind.sql_validation.validators.joins import JoinValidator
from querymind.sql_validation.validators.schema import SchemaValidator
from querymind.sql_validation.validators.syntax import SyntaxValidator
from querymind.sql_validation.validators.table import TableValidator


class Validator(Protocol):
    """One independent, read-only SQL check.

    Implementations never raise for an ordinary finding — every problem
    is returned as a `ValidationIssue` — and never call another
    validator or modify `parsed`.
    """

    @property
    def name(self) -> str:
        """A short, stable identifier for this validator, e.g. `"schema"`, `"join"`."""
        ...

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        """Inspect `parsed` and return every issue found (empty if none)."""
        ...


__all__ = [
    "AggregateValidator",
    "AliasValidator",
    "BusinessRuleValidator",
    "ColumnValidator",
    "DialectValidator",
    "FunctionValidator",
    "JoinValidator",
    "SchemaValidator",
    "SyntaxValidator",
    "TableValidator",
    "Validator",
]
