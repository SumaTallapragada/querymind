"""`POST /query/format` -- format a successful `SQLExecutionResult` into a `BusinessAnswer`.

Accepts a `SQLExecutionResult` directly as the whole request body (a
single required argument needs no wrapper DTO) and calls
`ResultFormatterEngine.format`. That engine only accepts a successful
execution -- a non-`SUCCESS` `SQLExecutionResult` raises `FormattingError`,
mapped by `querymind.api.exception_handlers` to `422 Unprocessable Entity`.

Requires at least `ANALYST` (Phase 22B) -- part of the same `/query/*` family, protected the
same way even though this one is pure formatting with no I/O of its own.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from querymind.api.dependencies import RateLimitQuery, RequireAnalyst, ResultFormatterEngineDep
from querymind.result_formatter.models import BusinessAnswer
from querymind.sql_execution.models import SQLExecutionResult

router = APIRouter(prefix="/query/format", tags=["query"])


@router.post(
    "",
    response_model=BusinessAnswer,
    status_code=status.HTTP_200_OK,
    summary="Format a successful execution result into a business answer",
    description=(
        "Converts a successful `SQLExecutionResult` into a deterministic, non-interpretive "
        "`BusinessAnswer` (a formatted table, a summary built only from the result's own "
        "shape, and an answer-type classification). Requires `execution_result.status` to "
        "already be `success`. Requires at least the `analyst` role."
    ),
)
async def format_result(
    execution_result: SQLExecutionResult,
    formatter: ResultFormatterEngineDep,
    _analyst: RequireAnalyst,
    _rate_limit: RateLimitQuery,
) -> BusinessAnswer:
    return formatter.format(execution_result)
