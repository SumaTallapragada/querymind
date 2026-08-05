"""AnswerGenerator: determines the `AnswerType` of a formatted result.

Uses only information already present on `SQLExecutionResult`/
`FormattedTable` -- row/column counts, and `SQLExecutionResult.executed_sql`
itself (parsed read-only with `sqlglot`, exactly as
`querymind.sql_execution.validator.ExecutionGuard` already does, to detect
aggregate functions / `GROUP BY`). Nothing here inspects the database or
re-runs any query.

Classification order (first match wins):

1. Zero rows                                          -> EMPTY_RESULT
2. Exactly one row, one column                         -> SCALAR
3. `executed_sql` contains an aggregate function
   (`SUM`/`COUNT`/`AVG`/`MIN`/`MAX`/...) or `GROUP BY`  -> AGGREGATION
4. Exactly one row, more than one column               -> DETAIL
5. Anything else (more than one row)                   -> TABLE
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from querymind.query_library.models import SQLDialect
from querymind.result_formatter.models import AnswerType, FormattedTable
from querymind.sql_execution import SQLExecutionResult

#: How `SQLExecutionResult.statistics.dialect` maps onto a sqlglot dialect string. Duplicated
#: (not imported) from `querymind.sql_execution.validator`'s own copy of this mapping -- a
#: private, underscore-prefixed name from another module is deliberately never imported across
#: a package boundary in this codebase; the mapping itself is tiny and stable.
_SQLGLOT_DIALECTS: dict[SQLDialect, str] = {
    SQLDialect.POSTGRESQL: "postgres",
    SQLDialect.MYSQL: "mysql",
    SQLDialect.SQLITE: "sqlite",
    SQLDialect.ANSI: "",
}


class AnswerGenerator:
    """Determines an `AnswerType`. Never executes, validates, or repairs SQL."""

    def determine(
        self, execution_result: SQLExecutionResult, formatted_table: FormattedTable
    ) -> AnswerType:
        row_count = len(formatted_table.rows)
        column_count = len(formatted_table.columns)

        if row_count == 0:
            return AnswerType.EMPTY_RESULT
        if row_count == 1 and column_count == 1:
            return AnswerType.SCALAR
        if self._is_aggregated(execution_result):
            return AnswerType.AGGREGATION
        if row_count == 1:
            return AnswerType.DETAIL
        return AnswerType.TABLE

    @staticmethod
    def _is_aggregated(execution_result: SQLExecutionResult) -> bool:
        dialect = _SQLGLOT_DIALECTS.get(execution_result.statistics.dialect, "postgres")
        try:
            statement = sqlglot.parse_one(execution_result.executed_sql, dialect=dialect)
        except SqlglotError:
            # Best-effort classification only -- a parse failure here (which should not
            # happen for SQL that already executed successfully) falls through to the
            # row-count-based rules rather than failing the whole answer.
            return False
        if statement is None:
            return False
        return statement.find(exp.AggFunc) is not None or statement.find(exp.Group) is not None
