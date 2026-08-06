"""Unit tests for `GET /api/v1/settings`. Real `SettingsDep` (the hermetic test `Settings`
fixture) -- no engine to mock, since this route only reads values already on `Settings`.
"""

from __future__ import annotations

from httpx import AsyncClient


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
