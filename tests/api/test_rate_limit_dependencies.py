"""Unit tests for the Phase 22D rate-limit dependency functions in `querymind.api.dependencies`
-- called directly as plain async functions with a fake `RateLimiter`, mirroring
`test_dependencies.py`'s own "call it directly, no HTTP needed" style for RBAC dependencies.
`tests/api/test_rate_limiting.py` covers the same behavior end to end through real HTTP
requests; this file isolates each dependency's own key-composition and blocking logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from starlette.requests import Request

from querymind.api.dependencies import (
    check_general_rate_limit,
    check_login_rate_limit,
    check_query_rate_limit,
    check_refresh_rate_limit,
    check_register_rate_limit,
)
from querymind.core.config import Settings
from querymind.security.exceptions import RateLimitExceededError
from querymind.security.rate_limiter import RateLimitDecision
from tests.api.conftest import make_user_read


@dataclass
class _FakeRateLimiter:
    """Records every `.check(...)` call (key, capacity, refill_per_second); returns a
    per-key configured decision, defaulting to "allowed" for any key not explicitly set.
    """

    decisions: dict[str, RateLimitDecision] = field(default_factory=dict)
    calls: list[tuple[str, int, float]] = field(default_factory=list)

    async def check(
        self, key: str, *, capacity: int, refill_per_second: float
    ) -> RateLimitDecision:
        self.calls.append((key, capacity, refill_per_second))
        return self.decisions.get(key, RateLimitDecision(allowed=True))


def _settings(**overrides: Any) -> Settings:
    return Settings(
        postgres_user="test",
        postgres_password="test",  # type: ignore[arg-type]
        postgres_db="test",
        postgres_host="localhost",
        log_format="console",
        **overrides,
    )


def _request(
    *,
    client_host: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
    json_body: dict[str, object] | None = None,
) -> Request:
    body_bytes = json.dumps(json_body).encode() if json_body is not None else b""
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": raw_headers,
        "client": (client_host, 12345),
    }
    return Request(scope, receive=receive)  # type: ignore[arg-type]


class TestGeneralRateLimit:
    async def test_allowed_does_not_raise(self) -> None:
        limiter = _FakeRateLimiter()

        await check_general_rate_limit(_request(), limiter, _settings())  # type: ignore[arg-type]

    async def test_blocked_raises_rate_limit_exceeded_error(self) -> None:
        limiter = _FakeRateLimiter(
            decisions={
                "general:ip:127.0.0.1": RateLimitDecision(allowed=False, retry_after_seconds=7.0)
            }
        )

        with pytest.raises(RateLimitExceededError) as exc_info:
            await check_general_rate_limit(_request(), limiter, _settings())  # type: ignore[arg-type]

        assert exc_info.value.retry_after_seconds == 7.0

    async def test_uses_the_configured_general_limit(self) -> None:
        limiter = _FakeRateLimiter()
        settings = _settings(rate_limit_general_per_minute=42)

        await check_general_rate_limit(_request(), limiter, settings)  # type: ignore[arg-type]

        key, capacity, refill = limiter.calls[0]
        assert key == "general:ip:127.0.0.1"
        assert capacity == 42
        assert refill == pytest.approx(42 / 60)

    async def test_separate_ips_use_separate_keys(self) -> None:
        limiter = _FakeRateLimiter()

        await check_general_rate_limit(_request(client_host="1.1.1.1"), limiter, _settings())  # type: ignore[arg-type]
        await check_general_rate_limit(_request(client_host="2.2.2.2"), limiter, _settings())  # type: ignore[arg-type]

        keys = [call[0] for call in limiter.calls]
        assert keys == ["general:ip:1.1.1.1", "general:ip:2.2.2.2"]

    async def test_error_message_never_leaks_the_bucket_key_or_capacity(self) -> None:
        limiter = _FakeRateLimiter(
            decisions={
                "general:ip:127.0.0.1": RateLimitDecision(allowed=False, retry_after_seconds=7.0)
            }
        )

        with pytest.raises(RateLimitExceededError) as exc_info:
            await check_general_rate_limit(_request(), limiter, _settings())  # type: ignore[arg-type]

        message = str(exc_info.value)
        assert "general:ip" not in message
        assert "127.0.0.1" not in message
        assert "300" not in message


class TestLoginRateLimit:
    async def test_checks_both_ip_and_username_buckets(self) -> None:
        limiter = _FakeRateLimiter()

        await check_login_rate_limit(
            _request(json_body={"username": "alice", "password": "x"}),
            limiter,  # type: ignore[arg-type]
            _settings(),
        )

        keys = [call[0] for call in limiter.calls]
        assert keys == ["login:ip:127.0.0.1", "login:username:alice"]

    async def test_blocked_by_ip_raises(self) -> None:
        limiter = _FakeRateLimiter(
            decisions={
                "login:ip:127.0.0.1": RateLimitDecision(allowed=False, retry_after_seconds=12.0)
            }
        )

        with pytest.raises(RateLimitExceededError):
            await check_login_rate_limit(
                _request(json_body={"username": "alice", "password": "x"}),
                limiter,  # type: ignore[arg-type]
                _settings(),
            )

    async def test_blocked_by_username_raises_even_from_a_fresh_ip(self) -> None:
        """The whole point of the username bucket: distributed credential stuffing against one
        account from many different IPs is still throttled by this bucket even though the IP
        bucket for each individual attacker IP never fills up.
        """
        limiter = _FakeRateLimiter(
            decisions={
                "login:username:mallory": RateLimitDecision(allowed=False, retry_after_seconds=12.0)
            }
        )

        with pytest.raises(RateLimitExceededError):
            await check_login_rate_limit(
                _request(client_host="9.9.9.9", json_body={"username": "mallory", "password": "x"}),
                limiter,  # type: ignore[arg-type]
                _settings(),
            )

    async def test_separate_usernames_use_separate_keys(self) -> None:
        limiter = _FakeRateLimiter()

        await check_login_rate_limit(
            _request(json_body={"username": "alice", "password": "x"}),
            limiter,  # type: ignore[arg-type]
            _settings(),
        )
        await check_login_rate_limit(
            _request(json_body={"username": "bob", "password": "x"}),
            limiter,  # type: ignore[arg-type]
            _settings(),
        )

        keys = {call[0] for call in limiter.calls}
        assert "login:username:alice" in keys
        assert "login:username:bob" in keys

    async def test_no_username_in_the_body_only_checks_ip(self) -> None:
        limiter = _FakeRateLimiter()

        await check_login_rate_limit(_request(json_body={}), limiter, _settings())  # type: ignore[arg-type]

        keys = [call[0] for call in limiter.calls]
        assert keys == ["login:ip:127.0.0.1"]


class TestRegisterRateLimit:
    async def test_uses_an_hourly_ip_bucket(self) -> None:
        limiter = _FakeRateLimiter()
        settings = _settings(rate_limit_register_per_hour=3)

        await check_register_rate_limit(_request(), limiter, settings)  # type: ignore[arg-type]

        key, capacity, refill = limiter.calls[0]
        assert key == "register:ip:127.0.0.1"
        assert capacity == 3
        assert refill == pytest.approx(3 / 3600)

    async def test_blocked_raises(self) -> None:
        limiter = _FakeRateLimiter(
            decisions={
                "register:ip:127.0.0.1": RateLimitDecision(
                    allowed=False, retry_after_seconds=1200.0
                )
            }
        )

        with pytest.raises(RateLimitExceededError):
            await check_register_rate_limit(_request(), limiter, _settings())  # type: ignore[arg-type]


class TestRefreshRateLimit:
    async def test_uses_a_per_minute_ip_bucket(self) -> None:
        limiter = _FakeRateLimiter()
        settings = _settings(rate_limit_refresh_per_minute=20)

        await check_refresh_rate_limit(_request(), limiter, settings)  # type: ignore[arg-type]

        key, capacity, refill = limiter.calls[0]
        assert key == "refresh:ip:127.0.0.1"
        assert capacity == 20
        assert refill == pytest.approx(20 / 60)

    async def test_blocked_raises(self) -> None:
        limiter = _FakeRateLimiter(
            decisions={
                "refresh:ip:127.0.0.1": RateLimitDecision(allowed=False, retry_after_seconds=3.0)
            }
        )

        with pytest.raises(RateLimitExceededError):
            await check_refresh_rate_limit(_request(), limiter, _settings())  # type: ignore[arg-type]


class TestQueryRateLimit:
    async def test_uses_the_authenticated_users_id(self) -> None:
        limiter = _FakeRateLimiter()
        user = make_user_read(id=42)
        settings = _settings(rate_limit_query_per_minute=30)

        await check_query_rate_limit(user, limiter, settings)  # type: ignore[arg-type]

        key, capacity, refill = limiter.calls[0]
        assert key == "query:user:42"
        assert capacity == 30
        assert refill == pytest.approx(30 / 60)

    async def test_separate_users_use_separate_keys(self) -> None:
        limiter = _FakeRateLimiter()

        await check_query_rate_limit(make_user_read(id=1), limiter, _settings())  # type: ignore[arg-type]
        await check_query_rate_limit(make_user_read(id=2), limiter, _settings())  # type: ignore[arg-type]

        keys = [call[0] for call in limiter.calls]
        assert keys == ["query:user:1", "query:user:2"]

    async def test_blocked_raises(self) -> None:
        limiter = _FakeRateLimiter(
            decisions={"query:user:7": RateLimitDecision(allowed=False, retry_after_seconds=2.0)}
        )

        with pytest.raises(RateLimitExceededError) as exc_info:
            await check_query_rate_limit(make_user_read(id=7), limiter, _settings())  # type: ignore[arg-type]

        assert exc_info.value.retry_after_seconds == 2.0
