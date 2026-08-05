"""A wrapper around the existing `SQLValidationEngine` — never a second validation engine.

`RepairValidator`'s only responsibility is calling
`SQLValidationEngine.validate()` on a repaired `GeneratedSQL` and
returning its `SQLValidationResult`. It duplicates none of that engine's
validator pipeline.
"""

from __future__ import annotations

from querymind.sql_generation.models import GeneratedSQL
from querymind.sql_validation.engine import SQLValidationEngine
from querymind.sql_validation.models import SQLValidationResult


class RepairValidator:
    """Validates repaired SQL via the existing `SQLValidationEngine`. Nothing more."""

    def __init__(self, validation_engine: SQLValidationEngine) -> None:
        self._validation_engine = validation_engine

    def validate(self, generated_sql: GeneratedSQL) -> SQLValidationResult:
        """Validate `generated_sql` via the existing `SQLValidationEngine` and return its result."""
        return self._validation_engine.validate(generated_sql)
