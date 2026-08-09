"""`GET /api/v1/health/live` needs no authentication (Phase 22B leaves it, and
`/api/v1/health/ready`, deliberately public -- see `querymind.api.v1.endpoints.health`'s
docstring: Docker/Compose's own `HEALTHCHECK` calls it with no credentials). The full report,
`GET /api/v1/health` below, requires only that the caller is authenticated (any role) --
`_authenticated` overrides `get_current_user` for every test in this file with a `VIEWER`, the
lowest rank, to demonstrate that no *specific* role is required, only login.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_current_user, get_health_check_engine
from querymind.auth.models import UserRole
from querymind.observability.models import HealthCheck, HealthReport, HealthStatus
from tests.api.conftest import make_user_read


@pytest.fixture(autouse=True)
def _authenticated(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)


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
