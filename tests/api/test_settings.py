"""Unit tests for `GET /api/v1/settings`. Real `SettingsDep` (the hermetic test `Settings`
fixture) -- no engine to mock, since this route only reads values already on `Settings`.

Requires `ADMIN` (Phase 22B) -- `_authenticated_as_admin` below overrides `get_current_user`
for every test in this file; see `test_diagnostics.py`'s identical fixture for why.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_current_user
from querymind.auth.models import UserRole
from tests.api.conftest import make_user_read


@pytest.fixture(autouse=True)
def _authenticated_as_admin(app: FastAPI) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user_read(role=UserRole.ADMIN)


async def test_returns_read_only_configuration(client: AsyncClient) -> None:
    response = await client.get("/api/v1/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["app_name"]
    assert body["environment"] == "development"
    assert body["database_engine"] == "PostgreSQL"
    assert body["database_name"] == "test"
    assert body["llm_provider"] == "claude"
    assert set(body["streaming_transports"]) == {"sse", "websocket"}


async def test_never_exposes_a_secret(client: AsyncClient) -> None:
    response = await client.get("/api/v1/settings")

    body = response.json()
    serialized = str(body).lower()
    assert "password" not in serialized
    assert "api_key" not in serialized
    assert "secret" not in serialized
