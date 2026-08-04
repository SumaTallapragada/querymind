"""Shallow, deterministic statement-type detection — not a SQL parser or validator.

`StatementTypeDetector` looks only at the SQL text's leading keyword, via
a plain string prefix match (with a word-boundary check, so an
identifier like `SELECTOR_TABLE` isn't mistaken for the keyword
`SELECT`). It does not build a syntax tree, does not check that the
statement is well-formed, and does not know whether the tables/columns
it references exist — that would cross into "validate SQL," which is
explicitly out of scope for this package. Its sole purpose is
descriptive metadata for `GeneratedSQL.statement_type`.
"""

from __future__ import annotations

from querymind.sql_generation.models import SQLStatementType

#: Ordered so a multi-word/compound keyword never gets shadowed by a shorter one —
#: not a concern with the current keyword set, but keeps the mapping self-documenting.
_LEADING_KEYWORDS: tuple[tuple[str, SQLStatementType], ...] = (
    ("WITH", SQLStatementType.WITH),
    ("SELECT", SQLStatementType.SELECT),
    ("INSERT", SQLStatementType.INSERT),
    ("UPDATE", SQLStatementType.UPDATE),
    ("DELETE", SQLStatementType.DELETE),
)


class StatementTypeDetector:
    """Sniffs the leading SQL keyword of a normalized SQL string via a plain prefix match."""

    def detect(self, sql: str) -> SQLStatementType:
        """Return the `SQLStatementType` matching `sql`'s leading keyword, or `UNKNOWN`."""
        upper = sql.strip().upper()
        for keyword, statement_type in _LEADING_KEYWORDS:
            if upper.startswith(keyword) and self._is_word_boundary(upper, len(keyword)):
                return statement_type
        return SQLStatementType.UNKNOWN

    @staticmethod
    def _is_word_boundary(text: str, index: int) -> bool:
        """Whether `text[index]` is not part of the same identifier as `text[:index]`."""
        return index >= len(text) or not (text[index].isalnum() or text[index] == "_")
