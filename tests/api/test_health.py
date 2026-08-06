from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_health_check_engine
from querymind.observability.models import HealthCheck, HealthReport, HealthStatus


async def test_liveness_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_liveness_sets_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")

    assert "X-Request-ID" in response.headers


# --- GET /api/v1/health -- full report, added Phase 16 -----------------------------------


class _FakeHealthCheckEngine:
    def __init__(self, report: HealthReport) -> None:
        self._report = report

    async def check(self) -> HealthReport:
        return self._report


def _make_report(status: HealthStatus) -> HealthReport:
    return HealthReport(
        checks=(HealthCheck(name="database", status=status),),
        overall_status=status,
        generated_at=datetime.now(UTC),
    )


async def test_full_health_report_returns_200_when_healthy(
    app: FastAPI, client: AsyncClient
) -> None:
    fake = _FakeHealthCheckEngine(_make_report(HealthStatus.HEALTHY))
    app.dependency_overrides[get_health_check_engine] = lambda: fake

    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["overall_status"] == "healthy"


async def test_full_health_report_returns_503_when_unhealthy(
    app: FastAPI, client: AsyncClient
) -> None:
    fake = _FakeHealthCheckEngine(_make_report(HealthStatus.UNHEALTHY))
    app.dependency_overrides[get_health_check_engine] = lambda: fake

    response = await client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["overall_status"] == "unhealthy"


async def test_full_health_report_does_not_collide_with_the_liveness_probe(
    app: FastAPI, client: AsyncClient
) -> None:
    fake = _FakeHealthCheckEngine(_make_report(HealthStatus.HEALTHY))
    app.dependency_overrides[get_health_check_engine] = lambda: fake

    live_response = await client.get("/api/v1/health/live")

    assert live_response.status_code == 200
    assert live_response.json() == {"status": "ok"}
