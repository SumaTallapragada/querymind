"""Domain-specific exceptions for the End-to-End QueryMind Orchestrator.

`PipelineExecutionError` carries every artifact and stage timing the
pipeline had already produced before the failing stage -- so
`QueryMindEngine.ask` (which catches it, and never raises itself) can
still populate `QueryMindResponse.statistics`/`.generated_sql`/etc. with
whatever real, partial progress was made, rather than discarding it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querymind.orchestrator.models import PipelineStage, StageTiming
    from querymind.sql_execution import SQLExecutionResult
    from querymind.sql_generation import GeneratedSQL
    from querymind.sql_repair import SQLRepairResult
    from querymind.sql_validation import SQLValidationResult


class QueryMindError(Exception):
    """Base class for every exception raised within `querymind.orchestrator`."""


class PipelineConfigurationError(QueryMindError):
    """Raised when `PipelineRunner`/`QueryMindEngine` is constructed with invalid collaborators."""


class PipelineExecutionError(QueryMindError):
    """Raised by `PipelineRunner.run` when a pipeline stage itself raises.

    Not raised for a stage that completes but reports a structured
    failure of its own (e.g. `SQLExecutionResult.status` not `SUCCESS`)
    -- that case never raises at all; `PipelineRunner.run` converts it
    directly into a `FAILED` `QueryMindResponse` instead, exactly like
    every other genuinely unexpected exception this class wraps.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: PipelineStage,
        stage_timings: tuple[StageTiming, ...],
        repair_attempted: bool,
        repair_performed: bool,
        generated_sql: GeneratedSQL | None,
        validation_result: SQLValidationResult | None,
        repair_result: SQLRepairResult | None,
        execution_result: SQLExecutionResult | None,
    ) -> None:
        self.stage = stage
        self.stage_timings = stage_timings
        self.repair_attempted = repair_attempted
        self.repair_performed = repair_performed
        self.generated_sql = generated_sql
        self.validation_result = validation_result
        self.repair_result = repair_result
        self.execution_result = execution_result
        super().__init__(message)
