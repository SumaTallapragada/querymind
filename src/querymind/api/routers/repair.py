"""`POST /query/repair` -- repair SQL that failed validation.

Accepts the original question (needed to rebuild retrieval context --
see `querymind.orchestrator.pipeline.PipelineRunner.repair_sql`'s
docstring for why) plus the failed `SQLValidationResult`. Returns a
`SQLRepairResult` regardless of whether repair actually succeeded --
check `status`, not the HTTP status code, for that.

Requires at least `ANALYST` (Phase 22B) -- calls the LLM, same as `POST /query`/`/query/sql`.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from querymind.api.dependencies import QueryMindEngineDep, RequireAnalyst
from querymind.api.models.request import RepairRequest
from querymind.sql_repair.models import SQLRepairResult

router = APIRouter(prefix="/query/repair", tags=["query"])


@router.post(
    "",
    response_model=SQLRepairResult,
    status_code=status.HTTP_200_OK,
    summary="Repair SQL that failed validation",
    description=(
        "Rebuilds retrieval context for `question`, then repairs `validation_result`'s SQL "
        "through a bounded, automatic retry loop against the LLM. `status` on the response "
        "(`repaired`/`max_attempts_reached`/`no_progress`/`unrepairable`) reports the outcome; "
        "a `200` only means the repair attempt itself completed, not that it succeeded. "
        "Requires at least the `analyst` role."
    ),
)
async def repair_sql(
    request: RepairRequest, engine: QueryMindEngineDep, _analyst: RequireAnalyst
) -> SQLRepairResult:
    return await engine.repair(request.question, request.validation_result)
