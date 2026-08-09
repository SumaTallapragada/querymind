"""Unit tests for `NoOpAuthenticationCache` -- mirrors `tests/sql_execution/test_cache.py`'s
coverage of `NoOpSQLExecutionCache` exactly: every operation is a well-defined no-op, never a
crash, never actually caching anything.
"""

from __future__ import annotations

from datetime import UTC, datetime

from querymind.auth.cache import AuthenticationCache, NoOpAuthenticationCache
from querymind.auth.models import User


def _user() -> User:
    user = User(username="alice", email="alice@example.com", password_hash="hash")
    user.id = 1
    user.is_active = True
    user.is_superuser = False
    user.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return user


class TestNoOpAuthenticationCache:
    def test_get_is_always_a_miss(self) -> None:
        cache = NoOpAuthenticationCache()
        assert cache.get("1") is None

    def test_set_then_get_is_still_a_miss(self) -> None:
        cache = NoOpAuthenticationCache()
        cache.set("1", _user())
        assert cache.get("1") is None

    def test_clear_never_raises(self) -> None:
        cache = NoOpAuthenticationCache()
        cache.clear()  # must not raise

    def test_satisfies_the_authentication_cache_protocol(self) -> None:
        cache: AuthenticationCache = NoOpAuthenticationCache()
        cache.set("1", _user())
        assert cache.get("1") is None
        cache.clear()
