"""The SQL Validation Engine — QueryMind Phase 11B.

Validates a `querymind.sql_generation.GeneratedSQL` before it may proceed
to execution: parses it with `sqlglot`, then runs ten independent,
read-only validators against the resulting AST plus the existing
Metadata Engine, Relationship Graph, and Business Knowledge Engine. It
does **not** generate, modify, repair, or optimize SQL, and does **not**
execute SQL or call an LLM — its only responsibility is validation.

The public surface is `SQLValidationEngine.validate`.
"""

from __future__ import annotations

from querymind.sql_validation.cache import NoOpSQLValidationCache, SQLValidationCache
from querymind.sql_validation.engine import SQLValidationEngine
from querymind.sql_validation.exceptions import (
    BusinessRuleViolationError,
    SchemaValidationError,
    SQLSyntaxError,
    SQLValidationError,
    UnsupportedDialectError,
)
from querymind.sql_validation.models import (
    SQLValidationResult,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatistics,
    ValidationWarning,
    ValidatorExecutionTime,
)
from querymind.sql_validation.parser import ParsedSQL, SQLParser
from querymind.sql_validation.registry import ValidatorRegistry, build_default_registry
from querymind.sql_validation.validators import (
    AggregateValidator,
    AliasValidator,
    BusinessRuleValidator,
    ColumnValidator,
    DialectValidator,
    FunctionValidator,
    JoinValidator,
    SchemaValidator,
    SyntaxValidator,
    TableValidator,
    Validator,
)

__all__ = [
    "AggregateValidator",
    "AliasValidator",
    "BusinessRuleValidator",
    "BusinessRuleViolationError",
    "ColumnValidator",
    "DialectValidator",
    "FunctionValidator",
    "JoinValidator",
    "NoOpSQLValidationCache",
    "ParsedSQL",
    "SQLParser",
    "SQLSyntaxError",
    "SQLValidationCache",
    "SQLValidationEngine",
    "SQLValidationError",
    "SQLValidationResult",
    "SchemaValidationError",
    "SchemaValidator",
    "SyntaxValidator",
    "TableValidator",
    "UnsupportedDialectError",
    "Validator",
    "ValidationIssue",
    "ValidationSeverity",
    "ValidationStatistics",
    "ValidationWarning",
    "ValidatorExecutionTime",
    "ValidatorRegistry",
    "build_default_registry",
]
