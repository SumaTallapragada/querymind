"""`GET /health/metrics` -- an immutable `MetricsSnapshot` of everything observed so far.

Reuses `querymind.observability.MetricsCollector.snapshot` directly.
Read-only: taking a snapshot never resets or mutates the collector's own
counters (see `InMemoryMetricsCollector`'s own docstring).
"""

from __future__ import annotations

from fastapi import APIRouter, status

from querymind.api.dependencies import MetricsCollectorDep
from querymind.observability.models import MetricsSnapshot

router = APIRouter(prefix="/health/metrics", tags=["health"])


@router.get(
    "",
    response_model=MetricsSnapshot,
    status_code=status.HTTP_200_OK,
    summary="A point-in-time metrics snapshot",
    description=(
        "Every `/query` call since process startup feeds this process' one "
        "`MetricsCollector` (pipeline run counts, per-stage latency, repair success rate, "
        "rows returned, LLM token usage, ...). This endpoint reads a snapshot of it -- it "
        "does not reset any counter."
    ),
)
async def metrics(metrics_collector: MetricsCollectorDep) -> MetricsSnapshot:
    return metrics_collector.snapshot()
