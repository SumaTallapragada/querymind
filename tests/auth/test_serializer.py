"""Unit tests for `AuthenticationSerializer` -- mirrors
`tests/sql_execution/test_serializer.py`'s coverage shape exactly, against a `UserRead`/
`TokenPair` instead of a `SQLExecutionResult`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import yaml

from querymind.auth.models import UserRole
from querymind.auth.schemas import TokenPair, UserRead
from querymind.auth.serializer import AuthenticationSerializer


def _user_read() -> UserRead:
    return UserRead(
        id=1,
        username="alice",
        email="alice@example.com",
        is_active=True,
        is_superuser=False,
        role=UserRole.ANALYST,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class TestToDict:
    def test_returns_a_plain_dict_with_every_field(self) -> None:
        result = AuthenticationSerializer.to_dict(_user_read())
        assert result["id"] == 1
        assert result["username"] == "alice"
        assert result["email"] == "alice@example.com"
        assert result["is_active"] is True
        assert result["is_superuser"] is False

    def test_datetimes_become_json_safe_strings(self) -> None:
        result = AuthenticationSerializer.to_dict(_user_read())
        assert isinstance(result["created_at"], str)

    def test_never_includes_a_password_hash_field(self) -> None:
        # UserRead has no password_hash field at all -- this is a schema-boundary guarantee,
        # not something the serializer itself filters.
        assert "password_hash" not in AuthenticationSerializer.to_dict(_user_read())


class TestToJson:
    def test_round_trips_through_json(self) -> None:
        import json

        text = AuthenticationSerializer.to_json(_user_read())
        parsed = json.loads(text)
        assert parsed["username"] == "alice"

    def test_indent_none_produces_a_single_line(self) -> None:
        text = AuthenticationSerializer.to_json(_user_read(), indent=None)
        assert "\n" not in text


class TestToYaml:
    def test_round_trips_through_yaml(self) -> None:
        text = AuthenticationSerializer.to_yaml(_user_read())
        parsed = yaml.safe_load(text)
        assert parsed["username"] == "alice"
        assert parsed["is_superuser"] is False

    def test_works_for_a_token_pair_too(self) -> None:
        tokens = TokenPair(access_token="a.b.c", refresh_token="d.e.f")
        text = AuthenticationSerializer.to_yaml(tokens)
        parsed = yaml.safe_load(text)
        assert parsed["token_type"] == "bearer"
