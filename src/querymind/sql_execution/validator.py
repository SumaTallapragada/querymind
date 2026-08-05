"""ExecutionGuard: the final, independent safety gate before SQL touches a real database.

Requires `SQLValidationResult.is_valid` — but never *trusts that alone*
for the single most safety-critical property, read-only-ness. Two real
gaps were found and closed here during development (see the package's
`ARCHITECTURAL NOTES` in the phase deliverable):

1. `sqlglot.parse_one` (used throughout `querymind.sql_validation`)
   silently parses only the *first* statement of a multi-statement
   string and discards the rest without error — `"SELECT 1; DROP TABLE
   customers;"` parses (and therefore validates) as a harmless
   `SELECT 1`, while the raw SQL *text* — which is what actually reaches
   the database — still contains the DROP. This guard uses
   `sqlglot.parse` (the list-returning form) and rejects anything but
   exactly one statement.

2. A statement rooted at `exp.Select` can still contain a write via a
   PostgreSQL "writable CTE" — `WITH deleted AS (DELETE FROM customers
   ... RETURNING *) SELECT * FROM deleted;` has `type(root) is Select`,
   passing a naive root-type check, while a `Delete` node sits inside its
   `WITH` clause. This guard walks the *entire* AST for any write node,
   not just the root.

Both gaps also apply to `querymind.sql_validation.validators.syntax.
SyntaxValidator`, which only checks `isinstance(root, exp.Select)` — a
latent issue in an existing, frozen phase, out of this phase's scope to
fix, flagged here rather than silently worked around upstream.

A third, independent, database-level defense also exists —
`DatabaseConnectionProvider` opens every connection read-only, so even a
write that somehow evaded every AST-level check here would still be
rejected by PostgreSQL itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from querymind.query_library.models import SQLDialect
from querymind.sql_execution.exceptions import (
    ExecutionRejectedError,
    SQLExecutionConfigurationError,
)
from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_validation.models import SQLValidationResult

#: Default per-query execution timeout, in seconds.
DEFAULT_EXECUTION_TIMEOUT_SECONDS = 30.0

#: How `GeneratedSQL.dialect` maps onto a sqlglot dialect string. Duplicated (not imported)
#: from `querymind.sql_validation.engine`'s private `_SQLGLOT_DIALECTS` -- a private,
#: underscore-prefixed name from another module is deliberately never imported across a
#: package boundary in this codebase; the mapping itself is tiny and stable.
_SQLGLOT_DIALECTS: dict[SQLDialect, str] = {
    SQLDialect.POSTGRESQL: "postgres",
    SQLDialect.MYSQL: "mysql",
    SQLDialect.SQLITE: "sqlite",
    SQLDialect.ANSI: "",
}

#: AST node types that indicate a write -- checked anywhere in the tree, not just the root,
#: specifically to catch a write hidden inside a writable CTE.
_WRITE_NODE_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Alter,
    exp.Drop,
    exp.TruncateTable,
    exp.Copy,
)


@dataclass(frozen=True, slots=True)
class ExecutionPermit:
    """What `ExecutionGuard` authorizes: the exact SQL text to run, and the timeout to bound it by."""

    sql: str
    timeout_seconds: float


class ExecutionGuard:
    """Determines whether execution is permitted. Never repairs SQL, never re-runs full validation."""

    def __init__(self, timeout_seconds: float = DEFAULT_EXECUTION_TIMEOUT_SECONDS) -> None:
        if timeout_seconds <= 0:
            raise SQLExecutionConfigurationError(
                f"timeout_seconds must be > 0, got {timeout_seconds!r}."
            )
        self._timeout_seconds = timeout_seconds

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    def check(
        self, generated_sql: GeneratedSQL, validation_result: SQLValidationResult
    ) -> ExecutionPermit:
        """Authorize execution of `generated_sql`. Raises `ExecutionRejectedError` if not permitted."""
        if not validation_result.is_valid:
            raise ExecutionRejectedError(
                "SQL did not pass validation (SQLValidationResult.is_valid is False)."
            )

        sql = generated_sql.sql.strip()
        if not sql:
            raise ExecutionRejectedError("SQL is empty.")

        dialect = _SQLGLOT_DIALECTS.get(generated_sql.dialect, "postgres")
        statements = [
            statement for statement in sqlglot.parse(sql, dialect=dialect) if statement is not None
        ]
        if len(statements) != 1:
            raise ExecutionRejectedError(
                f"Expected exactly one SQL statement, found {len(statements)}."
            )

        statement = statements[0]
        if not isinstance(statement, exp.Select):
            raise ExecutionRejectedError(
                f"Only SELECT (including WITH ... SELECT) statements are permitted; "
                f"got {type(statement).__name__.upper()}."
            )

        write_node = statement.find(*_WRITE_NODE_TYPES)
        if write_node is not None:
            raise ExecutionRejectedError(
                f"Statement contains a {type(write_node).__name__.upper()} operation, which is "
                "not read-only (e.g. inside a writable CTE)."
            )

        return ExecutionPermit(sql=sql, timeout_seconds=self._timeout_seconds)
