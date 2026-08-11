"""Unit tests for `/api/v1/auth/api-keys*` (Phase 22D). `AuthenticationServiceDep` is mocked,
mirroring `test_auth.py`'s own style exactly -- these tests verify each route's own
responsibilities (validating the body, calling the right service method with the right
arguments, mapping the result/exception to the right HTTP response), not `AuthenticationService`
itself (`tests/auth/test_service.py` covers that against a fake repository;
`test_auth_integration.py` against the real database).

`TestApiKeyCredentialsCannotManageApiKeys` is the one class that does *not* override the
identity dependency -- it exists specifically to prove the structural guarantee that an API key
can never be used against these three routes (see `CurrentUserJwtOnly`'s own docstring in
`querymind.api.dependencies`).
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from querymind.api.dependencies import get_authentication_service, get_current_user_jwt_only
from querymind.auth.exceptions import ApiKeyNotFoundError
from tests.api.conftest import (
    FakeAuthenticationService,
    UserRead,
    make_api_key_created,
    make_api_key_read,
    make_user_read,
)

_user_read = make_user_read
_api_key_read = make_api_key_read
_api_key_created = make_api_key_created


def _install(
    app: FastAPI, fake: FakeAuthenticationService, *, user: UserRead | None = None
) -> None:
    app.dependency_overrides[get_authentication_service] = lambda: fake
    if user is not None:
        app.dependency_overrides[get_current_user_jwt_only] = lambda: user


class TestCreateApiKey:
    async def test_returns_201_with_the_raw_key_and_metadata(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.create_api_key_result = _api_key_created()
        _install(app, fake, user=_user_read(id=3))

        response = await client.post("/api/v1/auth/api-keys", json={"name": "CI pipeline"})

        assert response.status_code == 201
        body = response.json()
        assert body["raw_key"].startswith("qm_")
        assert body["key"]["name"] == "CI pipeline"
        assert "key_hash" not in str(body).lower()

    async def test_creates_for_the_callers_own_user_id(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.create_api_key_result = _api_key_created()
        _install(app, fake, user=_user_read(id=99))

        await client.post("/api/v1/auth/api-keys", json={"name": "laptop"})

        assert fake.create_api_key_calls == [{"user_id": 99, "name": "laptop"}]

    async def test_an_empty_name_is_rejected_before_reaching_the_service(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        _install(app, fake, user=_user_read())

        response = await client.post("/api/v1/auth/api-keys", json={"name": ""})

        assert response.status_code == 422
        assert fake.create_api_key_calls == []

    async def test_without_a_jwt_returns_401(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        _install(app, fake)  # no user override -- the real get_current_user_jwt_only runs

        response = await client.post("/api/v1/auth/api-keys", json={"name": "no auth"})

        assert response.status_code == 401
        assert fake.create_api_key_calls == []


class TestListApiKeys:
    async def test_returns_200_with_the_callers_keys(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.list_api_keys_result = [
            _api_key_read(id=1, name="one"),
            _api_key_read(id=2, name="two"),
        ]
        _install(app, fake, user=_user_read(id=5))

        response = await client.get("/api/v1/auth/api-keys")

        assert response.status_code == 200
        assert [key["name"] for key in response.json()] == ["one", "two"]
        assert fake.list_api_keys_calls == [5]

    async def test_never_includes_a_hash_or_raw_key(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.list_api_keys_result = [_api_key_read()]
        _install(app, fake, user=_user_read())

        response = await client.get("/api/v1/auth/api-keys")

        serialized = str(response.json()).lower()
        assert "hash" not in serialized
        assert "raw_key" not in serialized


class TestRevokeApiKey:
    async def test_returns_204_with_no_body(self, app: FastAPI, client: AsyncClient) -> None:
        fake = FakeAuthenticationService()
        _install(app, fake, user=_user_read(id=1))

        response = await client.delete("/api/v1/auth/api-keys/42")

        assert response.status_code == 204
        assert response.content == b""

    async def test_calls_revoke_with_the_requesting_user_and_key_id(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        user = _user_read(id=7)
        _install(app, fake, user=user)

        await client.delete("/api/v1/auth/api-keys/42")

        assert fake.revoke_api_key_calls == [{"requesting_user": user, "key_id": 42}]

    async def test_an_unknown_or_not_owned_key_returns_404(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.revoke_api_key_exception = ApiKeyNotFoundError("not found")
        _install(app, fake, user=_user_read())

        response = await client.delete("/api/v1/auth/api-keys/999")

        assert response.status_code == 404
        assert response.json()["error_type"] == "ApiKeyNotFoundError"


class TestApiKeyCredentialsCannotManageApiKeys:
    """Structural guarantee: `CurrentUserJwtOnly` never consults `X-API-Key`, so a caller
    presenting one instead of a JWT is treated as unauthenticated on these three routes --
    proven by leaving `get_current_user_jwt_only` un-overridden (only `AuthenticationServiceDep`
    is faked) and configuring `authenticate_api_key` to succeed, which must never be reached.
    """

    async def test_an_x_api_key_header_alone_is_rejected_on_create(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = _user_read()
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "should not work"},
            headers={"X-API-Key": "qm_some-valid-looking-key"},
        )

        assert response.status_code == 401
        assert fake.authenticate_api_key_calls == []
        assert fake.create_api_key_calls == []

    async def test_an_x_api_key_header_alone_is_rejected_on_list(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = _user_read()
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.get(
            "/api/v1/auth/api-keys", headers={"X-API-Key": "qm_some-valid-looking-key"}
        )

        assert response.status_code == 401
        assert fake.authenticate_api_key_calls == []

    async def test_an_x_api_key_header_alone_is_rejected_on_revoke(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = _user_read()
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.delete(
            "/api/v1/auth/api-keys/1", headers={"X-API-Key": "qm_some-valid-looking-key"}
        )

        assert response.status_code == 401
        assert fake.authenticate_api_key_calls == []

    async def test_meanwhile_the_same_x_api_key_does_authenticate_an_ordinary_route(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """Confirms the negative tests above are meaningful -- the same key genuinely *does*
        work on an ordinary `CurrentUser` route (`/auth/me`), so its rejection on the management
        routes is `CurrentUserJwtOnly` specifically, not a broken test header.
        """
        fake = FakeAuthenticationService()
        fake.authenticate_api_key_result = _user_read(username="key_user")
        app.dependency_overrides[get_authentication_service] = lambda: fake

        response = await client.get(
            "/api/v1/auth/me", headers={"X-API-Key": "qm_some-valid-looking-key"}
        )

        assert response.status_code == 200
        assert response.json()["username"] == "key_user"
        assert fake.authenticate_api_key_calls == ["qm_some-valid-looking-key"]
