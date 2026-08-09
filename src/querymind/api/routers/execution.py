"""`POST /query/execute` -- execute validated SQL read-only against the real database.

Accepts a `SQLValidationResult` (which embeds the `GeneratedSQL` to run)
and calls `SQLExecutionEngine.execute` directly -- no orchestration,
since execution takes exactly the two inputs a caller already has after
`/query/sql` or `/query/validate`.

Requires at least `ANALYST` (Phase 22B) -- the one `/query/*` endpoint that reads real data
even without an LLM call; a `VIEWER` is not meant to trigger a database read on demand.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from querymind.api.dependencies import RequireAnalyst, SQLExecutionEngineDep
from querymind.api.models.request import ExecuteRequest
from querymind.sql_execution.models import SQLExecutionResult

router = APIRouter(prefix="/query/execute", tags=["query"])


@router.post(
    "",
    response_model=SQLExecutionResult,
    status_code=status.HTTP_200_OK,
    summary="Execute validated SQL read-only",
    description=(
        "Executes `validation_result.generated_sql` read-only against the real database, "
        "behind the same defense-in-depth guards (an AST-level read-only check plus a "
        "database-level read-only transaction) the full pipeline uses. Always returns a "
        "`SQLExecutionResult` -- check `status` (`success`/`failed`/`rejected`/`timeout`), not "
        "the HTTP status code, for the outcome. Requires at least the `analyst` role."
    ),
)
async def execute_sql(
    request: ExecuteRequest, execution_engine: SQLExecutionEngineDep, _analyst: RequireAnalyst
) -> SQLExecutionResult:
    return await execution_engine.execute(
        request.validation_result.generated_sql, request.validation_result
    )
