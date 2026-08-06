"""QueryMindEngine: the top-level, primary public entry point for the whole pipeline.

`ask` never raises -- it wraps `PipelineRunner.run` and converts any
failure into a `FAILED` `QueryMindResponse`:

- A `PipelineExecutionError` (a stage's own call genuinely raised) is
  converted using every artifact and stage timing it carried from the
  point of failure, so a `FAILED` response is still as complete and
  honest as possible.
- Any other exception (a defensive catch-all -- nothing in this
  package's own code is expected to raise one, but a caller must never
  see this method throw regardless) becomes a minimal `FAILED` response
  with just the total latency measured.

`ask_for_sql`/`repair` (added in Phase 16, for the FastAPI service
layer's `/query/sql`/`/query/repair` endpoints) are thin delegates to
`PipelineRunner.generate_sql`/`.repair_sql` with **no** such
never-raises guarantee -- `GeneratedSqlResult` and `SQLRepairResult`
have no `status`/`error` field for a converted failure to live in, so a
genuine stage failure simply propagates. Mapping that to an HTTP
response is the API layer's job (`querymind.api.exception_handlers`),
not this engine's.

`ask` (Phase 17) also accepts an optional `event_publisher`, passed
straight through to `PipelineRunner.run` -- `ask` itself needs no
awareness of *what* an event publisher does, only that `run` accepts
one; omitting it (every caller before Phase 17, and every caller that
isn't the streaming service layer) is a true no-op, verified by the full
pre-existing test suite passing unmodified.
"""

from __future__ import annotations

import time

from querymind.orchestrator.events import StageEventPublisher
from querymind.orchestrator.exceptions import PipelineExecutionError
from querymind.orchestrator.models import (
    GeneratedSqlResult,
    PipelineStatus,
    QueryMindResponse,
)
from querymind.orchestrator.pipeline import PipelineRunner
from querymind.orchestrator.statistics import PipelineStatisticsBuilder
from querymind.sql_repair import SQLRepairResult
from querymind.sql_validation import SQLValidationResult


class QueryMindEngine:
    """Answers one natural language question end-to-end. Orchestrates only."""

    def __init__(
        self,
        pipeline_runner: PipelineRunner,
        statistics_builder: PipelineStatisticsBuilder | None = None,
    ) -> None:
        self._pipeline_runner = pipeline_runner
        self._statistics_builder = statistics_builder or PipelineStatisticsBuilder()

    async def ask(
        self, question: str, *, event_publisher: StageEventPublisher | None = None
    ) -> QueryMindResponse:
        """Answer `question`. Never raises -- every failure becomes a FAILED `QueryMindResponse`.

        `event_publisher`, if given, is notified of pipeline/stage
        progress as `PipelineRunner.run` executes -- see that method's
        docstring. It changes nothing about what this method returns.
        """
        started = time.perf_counter()
        try:
            return await self._pipeline_runner.run(question, event_publisher=event_publisher)
        except PipelineExecutionError as exc:
            return QueryMindResponse(
                original_question=question,
                business_answer=None,
                generated_sql=exc.generated_sql,
                validation_result=exc.validation_result,
                repair_result=exc.repair_result,
                execution_result=exc.execution_result,
                statistics=self._statistics_builder.build(
                    total_latency_ms=self._elapsed_ms(started),
                    stage_timings=exc.stage_timings,
                    repair_attempted=exc.repair_attempted,
                    repair_performed=exc.repair_performed,
                ),
                status=PipelineStatus.FAILED,
                error=str(exc.__cause__) if exc.__cause__ is not None else str(exc),
            )
        except Exception as exc:  # last-resort safety net, see module docstring
            return QueryMindResponse(
                original_question=question,
                business_answer=None,
                generated_sql=None,
                validation_result=None,
                repair_result=None,
                execution_result=None,
                statistics=self._statistics_builder.build(
                    total_latency_ms=self._elapsed_ms(started),
                    stage_timings=(),
                    repair_attempted=False,
                    repair_performed=False,
                ),
                status=PipelineStatus.FAILED,
                error=str(exc),
            )

    async def ask_for_sql(self, question: str) -> GeneratedSqlResult:
        """Answer `question` up through SQL generation, validation, and conditional repair --
        never executing SQL. Raises `PipelineExecutionError` if any stage's own call raises;
        see the class docstring for why this method, unlike `ask`, does not catch it.
        """
        return await self._pipeline_runner.generate_sql(question)

    async def repair(
        self, question: str, validation_result: SQLValidationResult
    ) -> SQLRepairResult:
        """Repair `validation_result.generated_sql`, rebuilding retrieval context for `question`
        first. Raises on the same terms as `PipelineRunner.repair_sql` -- see its docstring.
        """
        return await self._pipeline_runner.repair_sql(question, validation_result)

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return (time.perf_counter() - started) * 1000
