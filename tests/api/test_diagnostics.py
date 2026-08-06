"""Unit tests for `GET /api/v1/health/diagnostics`. `DiagnosticsEngineDep` is mocked --
verifies the route returns `DiagnosticsEngine.run`'s report unchanged, and maps `503` only
when `overall_status` is `ERROR` (a `WARNING` overall status still returns `200`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_diagnostics_engine
from querymind.observability.models import DiagnosticFinding, DiagnosticsReport, DiagnosticStatus


class _FakeDiagnosticsEngine:
    def __init__(self, report: DiagnosticsReport) -> None:
        self._report = report

    async def run(self) -> DiagnosticsReport:
        return self._report


def _make_report(overall: DiagnosticStatus) -> DiagnosticsReport:
    return DiagnosticsReport(
        findings=(
            DiagnosticFinding(check_name="metadata_registry", status=overall, message="checked."),
        ),
        overall_status=overall,
        generated_at=datetime.now(UTC),
    )


async def test_returns_200_when_overall_status_is_pass(app: FastAPI, client: AsyncClient) -> None:
    fake = _FakeDiagnosticsEngine(_make_report(DiagnosticStatus.PASS))
    app.dependency_overrides[get_diagnostics_engine] = lambda: fake

    response = await client.get("/api/v1/health/diagnostics")

    assert response.status_code == 200
    assert response.json()["overall_status"] == "pass"


async def test_returns_200_when_overall_status_is_warning(
    app: FastAPI, client: AsyncClient
) -> None:
    fake = _FakeDiagnosticsEngine(_make_report(DiagnosticStatus.WARNING))
    app.dependency_overrides[get_diagnostics_engine] = lambda: fake

    response = await client.get("/api/v1/health/diagnostics")

    assert response.status_code == 200
    assert response.json()["overall_status"] == "warning"


async def test_returns_503_when_overall_status_is_error(app: FastAPI, client: AsyncClient) -> None:
    fake = _FakeDiagnosticsEngine(_make_report(DiagnosticStatus.ERROR))
    app.dependency_overrides[get_diagnostics_engine] = lambda: fake

    response = await client.get("/api/v1/health/diagnostics")

    assert response.status_code == 503
    assert response.json()["overall_status"] == "error"
