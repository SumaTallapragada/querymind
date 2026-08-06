"""`GET /health/diagnostics` -- a detailed `DiagnosticsReport`. Never modifies state.

Reuses `querymind.observability.DiagnosticsEngine` directly -- deeper and
more detailed than `/health` (a `PASS`/`WARNING`/`ERROR` plus a message
per check, including dependency versions and cache configuration), aimed
at a human debugging a problem rather than an automated probe.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from querymind.api.dependencies import DiagnosticsEngineDep
from querymind.observability.models import DiagnosticsReport, DiagnosticStatus

router = APIRouter(prefix="/health/diagnostics", tags=["health"])


@router.get(
    "",
    response_model=DiagnosticsReport,
    summary="Detailed diagnostics across every configured engine",
    description=(
        "Runs `DiagnosticsEngine.run` -- metadata registry, business knowledge, query "
        "library, relationship graph, prompt compiler, LLM configuration, database "
        "connectivity, dependency versions, and cache configuration. Each finding is "
        "`pass`/`warning`/`error`; the endpoint returns `503` only if `overall_status` is "
        "`error`."
    ),
)
async def diagnostics(
    response: Response, diagnostics_engine: DiagnosticsEngineDep
) -> DiagnosticsReport:
    report = await diagnostics_engine.run()
    if report.overall_status is DiagnosticStatus.ERROR:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
