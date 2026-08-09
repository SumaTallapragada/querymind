"""`POST /query` -- the primary endpoint: a natural language question in, a `QueryMindResponse` out.

The route does exactly three things: validate the request body (FastAPI,
via `QuestionRequest`), resolve `QueryMindEngineDep`, and call
`QueryMindEngine.ask`. `QueryMindEngine.ask` never raises, so this route
needs no exception handling of its own -- every possible outcome
(success or failure) is already a `QueryMindResponse` with a `status`
field, returned as-is.

Requires at least `ANALYST` (Phase 22B) -- running the pipeline calls the LLM and (via
execution) reads real data; a `VIEWER` is not meant to trigger either. `RequireAnalyst` is
ranked, so `ADMIN` satisfies this too -- see its own docstring.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from querymind.api.dependencies import MetricsCollectorDep, QueryMindEngineDep, RequireAnalyst
from querymind.api.models.request import QuestionRequest
from querymind.observability.metrics import MetricsCollector
from querymind.orchestrator.models import PipelineStatus, QueryMindResponse

router = APIRouter(prefix="/query", tags=["query"])


def _record_metrics(collector: MetricsCollector, response: QueryMindResponse) -> None:
    """Feed one completed `QueryMindResponse` into `collector`. Passive -- reads the already-
    returned response, never mutates it or influences what was returned to the caller.
    """
    collector.record_pipeline_run(
        success=response.status is PipelineStatus.SUCCESS,
        latency_ms=response.statistics.total_latency_ms,
        repair_attempted=response.statistics.repair_attempted,
        repair_succeeded=response.statistics.repair_performed,
    )
    for timing in response.statistics.stage_timings:
        collector.record_stage_latency(timing.stage.value, timing.latency_ms)
    if response.execution_result is not None and response.execution_result.query_result is not None:
        collector.record_sql_execution(
            rows_returned=response.execution_result.query_result.row_count
        )
    if response.generated_sql is not None:
        token_usage = response.generated_sql.llm_metrics.token_usage
        collector.record_llm_token_usage(
            prompt_tokens=token_usage.prompt_tokens, completion_tokens=token_usage.completion_tokens
        )
    if response.validation_result is not None and not response.validation_result.is_valid:
        collector.record_validation_failure()


@router.post(
    "",
    response_model=QueryMindResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a natural language question end to end",
    description=(
        "Runs the complete QueryMind pipeline: NLU, schema linking, business knowledge, "
        "retrieval, prompt compilation, SQL generation, validation, conditional repair, "
        "execution, and result formatting. Always returns a `QueryMindResponse` -- check "
        "`status` (`success`/`failed`) rather than the HTTP status code to distinguish a "
        "pipeline-level failure (still a `200`) from a transport-level one. Requires at least "
        "the `analyst` role."
    ),
    responses={
        200: {
            "description": "The pipeline ran to completion. `status` may still be `failed`.",
            "content": {
                "application/json": {
                    "example": {
                        "original_question": "Who are our top 5 customers by revenue?",
                        "status": "success",
                        "error": None,
                    }
                }
            },
        }
    },
)
async def ask_question(
    request: QuestionRequest,
    engine: QueryMindEngineDep,
    metrics_collector: MetricsCollectorDep,
    _analyst: RequireAnalyst,
) -> QueryMindResponse:
    response = await engine.ask(request.question)
    _record_metrics(metrics_collector, response)
    return response
