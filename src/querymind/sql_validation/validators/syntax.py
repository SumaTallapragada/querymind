"""Checks the parsed statement is one this engine actually supports.

Whether sqlglot could parse the SQL *at all* is already settled by the
time any validator runs — `querymind.sql_validation.parser.SQLParser`
raises `SQLSyntaxError` on a genuine parse failure, and
`SQLValidationEngine` catches that before the validator pipeline starts.
`SyntaxValidator`'s own, narrower job is the one syntax-adjacent check
that still needs the successfully-parsed AST: is this a *supported query
statement*? A read-only analytics engine has no business validating (or
ever having been asked to generate) `INSERT`/`UPDATE`/`DELETE`/`MERGE`/
`CREATE`/`ALTER`/`DROP`/`TRUNCATE`/`COPY`/....

Statement type is determined from the sqlglot AST's own node type —
never from the raw SQL text — via `_SUPPORTED_STATEMENT_TYPES`, the
single source of truth for what this validator accepts. A `WITH ... AS
(...) SELECT ...` query does **not** parse to a standalone `exp.With`
root node: sqlglot always roots a statement at its ultimate DML node
(`exp.Select`, `exp.Insert`, ...), attaching the CTE definitions as a
`with` argument on *that* node. `exp.With` only ever appears as an
attached sub-node (`ast.args["with"]`), never as `type(ast)` itself.
Supporting `exp.Select` therefore already covers a plain `SELECT` and a
CTE-prefixed `WITH ... SELECT ...` alike — and correctly continues to
reject a CTE-prefixed `WITH ... INSERT ...`, whose root node is
`exp.Insert`, not `exp.Select`.
"""

from __future__ import annotations

from sqlglot import exp

from querymind.sql_validation.models import ValidationIssue, ValidationSeverity
from querymind.sql_validation.parser import ParsedSQL

#: Statement AST root types this engine accepts. `exp.Select` covers both a plain
#: `SELECT` and a CTE-prefixed `WITH ... SELECT ...` — see the module docstring.
_SUPPORTED_STATEMENT_TYPES: tuple[type[exp.Expression], ...] = (exp.Select,)


class SyntaxValidator:
    """Confirms the parsed statement is a supported query statement (`SELECT`, incl. `WITH` CTEs)."""

    name = "syntax"

    def validate(self, parsed: ParsedSQL) -> tuple[ValidationIssue, ...]:
        if isinstance(parsed.ast, _SUPPORTED_STATEMENT_TYPES):
            return ()
        statement_type = type(parsed.ast).__name__.upper()
        return (
            ValidationIssue(
                code="unsupported_statement_type",
                severity=ValidationSeverity.ERROR,
                message=f"Statement type {statement_type!r} is not supported by QueryMind.",
                related_object=statement_type,
            ),
        )
