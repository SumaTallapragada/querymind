"""Unit tests for `querymind.auth.schemas` -- every model is frozen and rejects unexpected
fields; this file checks both properties hold for real, plus each model's own validation rules.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from querymind.auth.models import UserRole
from querymind.auth.schemas import (
    AuthenticationResult,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserRead,
)

_MODELS_AND_KWARGS = (
    (UserCreate, {"username": "alice", "email": "alice@example.com", "password": "password123"}),
    (UserLogin, {"username": "alice", "password": "password123"}),
    (TokenPair, {"access_token": "a.b.c", "refresh_token": "d.e.f"}),
    (RefreshRequest, {"refresh_token": "d.e.f"}),
)


class TestFrozenAndForbidExtra:
    @pytest.mark.parametrize(("model_type", "kwargs"), _MODELS_AND_KWARGS)
    def test_instances_are_frozen(self, model_type: type, kwargs: dict[str, str]) -> None:
        instance = model_type(**kwargs)
        first_field = next(iter(kwargs))
        with pytest.raises(ValidationError):
            setattr(instance, first_field, "changed")

    @pytest.mark.parametrize(("model_type", "kwargs"), _MODELS_AND_KWARGS)
    def test_rejects_an_unexpected_field(self, model_type: type, kwargs: dict[str, str]) -> None:
        with pytest.raises(ValidationError):
            model_type(**kwargs, unexpected_field="surprise")


class TestUserCreate:
    def test_accepts_a_valid_registration(self) -> None:
        user = UserCreate(username="alice", email="alice@example.com", password="password123")
        assert user.username == "alice"
        assert user.email == "alice@example.com"

    def test_rejects_a_malformed_email(self) -> None:
        with pytest.raises(ValidationError):
            UserCreate(username="alice", email="not-an-email", password="password123")

    def test_rejects_a_too_short_username(self) -> None:
        with pytest.raises(ValidationError):
            UserCreate(username="ab", email="alice@example.com", password="password123")

    def test_rejects_a_too_short_password(self) -> None:
        with pytest.raises(ValidationError):
            UserCreate(username="alice", email="alice@example.com", password="short")


class TestUserRead:
    def test_builds_from_an_orm_instance_via_from_attributes(self) -> None:
        from querymind.auth.models import User

        user = User(username="alice", email="alice@example.com", password_hash="hash")
        user.id = 1
        user.is_active = True
        user.is_superuser = False
        user.role = UserRole.ANALYST
        user.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        user.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

        read = UserRead.model_validate(user)

        assert read.id == 1
        assert read.username == "alice"

    def test_has_no_password_hash_field(self) -> None:
        assert "password_hash" not in UserRead.model_fields


class TestTokenPair:
    def test_defaults_token_type_to_bearer(self) -> None:
        tokens = TokenPair(access_token="a.b.c", refresh_token="d.e.f")
        assert tokens.token_type == "bearer"


class TestAuthenticationResult:
    def test_bundles_a_user_and_a_token_pair(self) -> None:
        user = UserRead(
            id=1,
            username="alice",
            email="alice@example.com",
            is_active=True,
            is_superuser=False,
            role=UserRole.ANALYST,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        tokens = TokenPair(access_token="a.b.c", refresh_token="d.e.f")

        result = AuthenticationResult(user=user, tokens=tokens)

        assert result.user is user
        assert result.tokens is tokens
