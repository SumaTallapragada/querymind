"""Route-level authorization tests (Phase 22B) -- the 401/403 boundary of the protected-route
matrix, across HTTP, for every route category this phase adds a role requirement to.

Deliberately scoped to just that boundary, not full 200-path behavior: every protected route's
own test file (`test_diagnostics.py`, `test_metrics.py`, `test_settings.py`, `test_query.py`,
`test_sql.py`, `test_validation.py`, `test_repair.py`, `test_execution.py`, `test_formatting.py`,
`tests/streaming/test_sse.py`, `test_health.py`) already exercises its 200 path under its own
`autouse` authentication fixture; duplicating that here would just re-prove the same thing twice.
A role check also runs as a `Depends()`, before the route body ever executes -- so these tests
never need to mock the engine behind a route, only the caller's role, matching
`test_dependencies.py`'s own "call it directly, no engine needed" scoping one layer up (this
file is the HTTP-level equivalent: does the *route* actually enforce what `test_dependencies.py`
already proved the underlying dependency function does).

`RequireAnalyst`-gated siblings not covered below (`/query/repair`, `/query/execute`,
`/query/format`, `POST /query/stream`, `tests/streaming/test_websocket.py`'s `/ws/query`) all
resolve through the exact same `get_analyst_required_user` that `/query`, `/query/sql`, and
`/query/validate` below already exercise at the HTTP layer -- see
`test_dependencies.py::TestGetAnalystRequiredUser` for the one place their shared behavior is
unit-tested directly, rather than once per route here.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_current_user
from querymind.auth.models import UserRole
from tests.api.conftest import make_user_read


class TestAdminOnlyRoutes:
    """`GET /api/v1/health/diagnostics`, `GET /api/v1/health/metrics`, `GET /api/v1/settings`."""

    async def test_diagnostics_without_a_token_is_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/diagnostics")
        assert response.status_code == 401

    async def test_diagnostics_as_an_analyst_is_403(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ANALYST)
        response = await client.get("/api/v1/health/diagnostics")
        assert response.status_code == 403

    async def test_metrics_without_a_token_is_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/metrics")
        assert response.status_code == 401

    async def test_metrics_as_a_viewer_is_403(self, app: FastAPI, client: AsyncClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)
        response = await client.get("/api/v1/health/metrics")
        assert response.status_code == 403

    async def test_settings_without_a_token_is_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/settings")
        assert response.status_code == 401

    async def test_settings_as_an_analyst_is_403(self, app: FastAPI, client: AsyncClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ANALYST)
        response = await client.get("/api/v1/settings")
        assert response.status_code == 403


class TestAnalystOrAdminRoutes:
    """`POST /api/v1/query`, `POST /api/v1/query/sql`, `POST /api/v1/query/validate` -- ranked,
    so `ADMIN` satisfies these too, not only `ANALYST`.
    """

    async def test_query_without_a_token_is_401(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/query", json={"question": "Who are our customers?"})
        assert response.status_code == 401

    async def test_query_as_a_viewer_is_403(self, app: FastAPI, client: AsyncClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)
        response = await client.post("/api/v1/query", json={"question": "Who are our customers?"})
        assert response.status_code == 403

    async def test_query_sql_without_a_token_is_401(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/query/sql", json={"question": "Who are our customers?"}
        )
        assert response.status_code == 401

    async def test_query_sql_as_a_viewer_is_403(self, app: FastAPI, client: AsyncClient) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)
        response = await client.post(
            "/api/v1/query/sql", json={"question": "Who are our customers?"}
        )
        assert response.status_code == 403

    async def test_query_validate_without_a_token_is_401(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/query/validate", json={"sql": "SELECT 1;"})
        assert response.status_code == 401

    async def test_query_validate_as_a_viewer_is_403(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)
        response = await client.post("/api/v1/query/validate", json={"sql": "SELECT 1;"})
        assert response.status_code == 403


class TestAnyAuthenticatedRoute:
    """`GET /api/v1/health` -- authenticated (any role), no specific role required."""

    async def test_without_a_token_is_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 401

    async def test_a_viewer_is_not_403(self, app: FastAPI, client: AsyncClient) -> None:
        """Never `403` for *any* authenticated role -- may still be `503` (an unhealthy real
        dependency), which is the health check's own business, not authorization's.
        """
        app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.VIEWER)
        response = await client.get("/api/v1/health")
        assert response.status_code != 403


class TestPublicHealthProbesStayUnauthenticated:
    """`GET /api/v1/health/live` and `/ready` -- deliberately exempt (Phase 22B); see
    `querymind.api.v1.endpoints.health`'s own docstring for why (Docker/Compose's own
    `HEALTHCHECK` calls `/live` with no credentials).
    """

    async def test_liveness_needs_no_token(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
