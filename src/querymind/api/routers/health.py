"""`GET /health` -- a full `HealthReport` across every configured engine. Executes no SQL.

Distinct from the pre-existing `/api/v1/health/live`/`/api/v1/health/ready`
probes (`querymind.api.v1.endpoints.health`, unchanged since Phase 1,
which this router does not replace or duplicate): those answer the
narrow "is this process alive/ready for traffic" question a container
orchestrator asks on a schedule; this one answers "is every engine this
pipeline depends on actually healthy," reusing
`querymind.observability.HealthCheckEngine` directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from querymind.api.dependencies import HealthCheckEngineDep
from querymind.observability.models import HealthReport, HealthStatus

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=HealthReport,
    summary="Full health report across every configured engine",
    description=(
        "Runs `HealthCheckEngine.check` -- database reachability, metadata/business "
        "knowledge/query examples loaded, prompt compiler ready, LLM configured, SQL "
        "validator/repair engine ready. Returns `503` if `overall_status` is `unhealthy`, "
        "`200` otherwise (including `unknown`, when a check's collaborator isn't configured)."
    ),
)
async def health(response: Response, health_check_engine: HealthCheckEngineDep) -> HealthReport:
    report = await health_check_engine.check()
    if report.overall_status is HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
