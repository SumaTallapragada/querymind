"""Unit tests for `GET /api/v1/health/metrics`. `MetricsCollectorDep` is mocked -- verifies
the route returns `MetricsCollector.snapshot()` unchanged, and never resets/mutates it.

Requires `ADMIN` (Phase 22B) -- `_authenticated_as_admin` below overrides `get_current_user`
for every test in this file; see `test_diagnostics.py`'s identical fixture for why.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_current_user, get_metrics_collector
from querymind.auth.models import UserRole
from querymind.observability.metrics import InMemoryMetricsCollector
from tests.api.conftest import make_user_read


@pytest.fixture(autouse=True)
def _authenticated_as_admin(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ADMIN)


async def test_returns_a_snapshot_of_recorded_metrics(app: FastAPI, client: AsyncClient) -> None:
    collector = InMemoryMetricsCollector()
    collector.record_pipeline_run(
        success=True, latency_ms=12.5, repair_attempted=False, repair_succeeded=False
    )
    app.dependency_overrides[get_metrics_collector] = lambda: collector

    response = await client.get("/api/v1/health/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_run_count"] == 1
    assert body["pipeline_success_count"] == 1


async def test_taking_a_snapshot_does_not_reset_the_collector(
    app: FastAPI, client: AsyncClient
) -> None:
    collector = InMemoryMetricsCollector()
    collector.record_pipeline_run(
        success=True, latency_ms=1.0, repair_attempted=False, repair_succeeded=False
    )
    app.dependency_overrides[get_metrics_collector] = lambda: collector

    await client.get("/api/v1/health/metrics")
    second_response = await client.get("/api/v1/health/metrics")

    assert second_response.json()["pipeline_run_count"] == 1


async def test_an_empty_collector_reports_zero_counts(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_metrics_collector] = lambda: InMemoryMetricsCollector()

    response = await client.get("/api/v1/health/metrics")

    assert response.status_code == 200
    assert response.json()["pipeline_run_count"] == 0
