"""`POST /query/sql` -- SQL generation, validation, and conditional repair. Never executes SQL.

Returns `GeneratedSQL`, `SQLValidationResult`, and `SQLRepairResult` (if
repair ran) without touching the database at all -- a "preview" of what
`POST /query` would run, for a caller that wants to inspect or approve
the SQL before it executes.

Requires at least `ANALYST` (Phase 22B) -- same reasoning as `POST /query`; this still calls
the LLM, just stops before execution.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from querymind.api.dependencies import QueryMindEngineDep, RequireAnalyst
from querymind.api.models.request import QuestionRequest
from querymind.orchestrator.models import GeneratedSqlResult

router = APIRouter(prefix="/query/sql", tags=["query"])


@router.post(
    "",
    response_model=GeneratedSqlResult,
    status_code=status.HTTP_200_OK,
    summary="Generate and validate SQL for a question, without executing it",
    description=(
        "Runs NLU through SQL generation, validation, and conditional repair -- stopping "
        "before execution and result formatting. Use this to preview or approve SQL before "
        "running `/query/execute` against it. Requires at least the `analyst` role."
    ),
    responses={
        200: {
            "description": "SQL was generated and validated (and repaired, if necessary).",
            "content": {
                "application/json": {
                    "example": {
                        "original_question": "Who are our top 5 customers by revenue?",
                        "generated_sql": {"sql": "SELECT ... LIMIT 5;"},
                        "repair_result": None,
                    }
                }
            },
        }
    },
)
async def generate_sql(
    request: QuestionRequest, engine: QueryMindEngineDep, _analyst: RequireAnalyst
) -> GeneratedSqlResult:
    return await engine.ask_for_sql(request.question)
