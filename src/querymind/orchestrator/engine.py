"""QueryMindEngine: the top-level, never-throws public entry point for the whole pipeline.

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
"""

from __future__ import annotations

import time

from querymind.orchestrator.exceptions import PipelineExecutionError
from querymind.orchestrator.models import PipelineStatus, QueryMindResponse
from querymind.orchestrator.pipeline import PipelineRunner
from querymind.orchestrator.statistics import PipelineStatisticsBuilder


class QueryMindEngine:
    """Answers one natural language question end-to-end. Orchestrates only."""

    def __init__(
        self,
        pipeline_runner: PipelineRunner,
        statistics_builder: PipelineStatisticsBuilder | None = None,
    ) -> None:
        self._pipeline_runner = pipeline_runner
        self._statistics_builder = statistics_builder or PipelineStatisticsBuilder()

    async def ask(self, question: str) -> QueryMindResponse:
        """Answer `question`. Never raises -- every failure becomes a FAILED `QueryMindResponse`."""
        started = time.perf_counter()
        try:
            return await self._pipeline_runner.run(question)
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

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return (time.perf_counter() - started) * 1000
