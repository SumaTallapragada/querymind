"""`GET /health` -- a full `HealthReport` across every configured engine. Executes no SQL.

Distinct from the pre-existing `/api/v1/health/live`/`/api/v1/health/ready`
probes (`querymind.api.v1.endpoints.health`, unchanged since Phase 1,
which this router does not replace or duplicate): those answer the
narrow "is this process alive/ready for traffic" question a container
orchestrator asks on a schedule; this one answers "is every engine this
pipeline depends on actually healthy," reusing
`querymind.observability.HealthCheckEngine` directly.

Requires authentication, any role (Phase 22B) -- `CurrentUser`, not a `Require*` role
dependency: per-engine health status isn't as sensitive as `/health/diagnostics`'s dependency
versions/cache configuration (which requires `ADMIN`), but still shouldn't be exposed
anonymously. `/health/live`/`/health/ready` (`v1.endpoints.health`) deliberately stay
unauthenticated -- see that module and the Phase 22B deliverable report's route-protection
matrix for why (Docker/Compose's own `HEALTHCHECK` calls `/health/live` with no credentials).
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from querymind.api.dependencies import CurrentUser, HealthCheckEngineDep
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
        "`200` otherwise (including `unknown`, when a check's collaborator isn't configured). "
        "Requires authentication (any role)."
    ),
)
async def health(
    response: Response, health_check_engine: HealthCheckEngineDep, _user: CurrentUser
) -> HealthReport:
    report = await health_check_engine.check()
    if report.overall_status is HealthStatus.UNHEALTHY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report
