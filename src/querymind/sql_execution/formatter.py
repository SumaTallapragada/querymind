"""ResultFormatter: converts raw database rows into immutable result models.

Responsibilities only: build `QueryColumn`/`QueryRow`/`QueryResult` from
a `RawQueryResult`. No business interpretation, no markdown, no
natural-language summaries — rows are returned exactly as the database
produced them.
"""

from __future__ import annotations

from querymind.sql_execution.exceptions import ResultFormattingError
from querymind.sql_execution.executor import RawQueryResult
from querymind.sql_execution.models import QueryColumn, QueryResult, QueryRow

#: PostgreSQL built-in type OIDs -> (database type name, Python type name), covering every
#: type QueryMind's own schema uses. asyncpg's cursor metadata exposes only the numeric OID
#: (verified against a real PostgreSQL instance during development — `cursor.description`'s
#: `null_ok` field is always `None`, hence `QueryColumn.nullable` is always `None` too), not a
#: human-readable name, so this is a deliberate, static, dependency-free lookup rather than a
#: live `pg_type` catalog query. An OID not listed here falls back to its own numeric string.
_POSTGRES_OID_TYPES: dict[int, tuple[str, str]] = {
    16: ("boolean", "bool"),
    20: ("bigint", "int"),
    21: ("smallint", "int"),
    23: ("integer", "int"),
    25: ("text", "str"),
    114: ("json", "dict"),
    700: ("real", "float"),
    701: ("double precision", "float"),
    1042: ("char", "str"),
    1043: ("varchar", "str"),
    1082: ("date", "date"),
    1083: ("time", "time"),
    1114: ("timestamp", "datetime"),
    1184: ("timestamptz", "datetime"),
    1700: ("numeric", "Decimal"),
    2950: ("uuid", "UUID"),
    3802: ("jsonb", "dict"),
}


class ResultFormatter:
    """Formats a `RawQueryResult` into an immutable `QueryResult`. Formats only."""

    def format(self, raw: RawQueryResult) -> QueryResult:
        """Convert `raw` into a `QueryResult`. Values are carried through unmodified.

        Raises `ResultFormattingError` if `raw`'s column names and type
        OIDs don't line up — internally inconsistent input `SQLExecutor`
        should never actually produce, but formatting is where it would
        surface rather than failing silently or crashing on a `zip`.
        """
        try:
            columns = tuple(
                self._column(name, type_oid)
                for name, type_oid in zip(raw.column_names, raw.column_type_oids, strict=True)
            )
        except ValueError as exc:
            raise ResultFormattingError(
                f"column_names ({len(raw.column_names)}) and column_type_oids "
                f"({len(raw.column_type_oids)}) have different lengths."
            ) from exc
        rows = tuple(QueryRow(values=row) for row in raw.rows)
        return QueryResult(columns=columns, rows=rows, row_count=len(rows))

    @staticmethod
    def _column(name: str, type_oid: int | None) -> QueryColumn:
        database_type, python_type = _POSTGRES_OID_TYPES.get(
            type_oid if type_oid is not None else -1, (f"oid:{type_oid}", "object")
        )
        return QueryColumn(
            name=name, database_type=database_type, python_type=python_type, nullable=None
        )
