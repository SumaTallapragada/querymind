"""Deterministic, cosmetic-only SQL text normalization.

Never changes what a SQL statement *means* — no keyword-casing changes,
no re-indentation, no query rewriting, nothing that could be mistaken
for repair. Only line-ending and surrounding-whitespace cleanup, plus
collapsing however many trailing semicolons/blank space the LLM
produced down to exactly one — a statement-terminator convention, not a
correctness fix, so it stays well inside "normalize", not "repair".
"""

from __future__ import annotations

import re

#: Matches every semicolon and whitespace character trailing the SQL, so it can be
#: collapsed down to exactly one terminating semicolon.
_TRAILING_SEMICOLONS_AND_WHITESPACE = re.compile(r"[;\s]+$")


class SQLNormalizer:
    """Normalizes extracted SQL text: line endings, surrounding whitespace, one trailing semicolon."""

    def normalize(self, sql: str) -> str:
        """Return a cosmetically normalized copy of `sql`. Never changes its meaning."""
        normalized = sql.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = _TRAILING_SEMICOLONS_AND_WHITESPACE.sub("", normalized)
        return f"{normalized};"
