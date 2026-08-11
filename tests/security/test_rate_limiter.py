"""Unit tests for `querymind.security.rate_limiter` -- pure, no I/O, no real database.
`InMemoryTokenBucketRateLimiter` is tested against an injected fake clock throughout (never
`asyncio.sleep`), mirroring `tests/observability/test_logger.py`-style "inject a clock" tests
elsewhere in this project.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from querymind.security.rate_limiter import InMemoryTokenBucketRateLimiter, NoOpRateLimiter


class _FakeClock:
    """A mutable, injectable clock -- `advance(seconds)` moves it forward; tests never sleep."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start if start is not None else datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> _FakeClock:
    return _FakeClock()


@pytest.fixture
def limiter(clock: _FakeClock) -> InMemoryTokenBucketRateLimiter:
    return InMemoryTokenBucketRateLimiter(clock=clock)


class TestBucketExhaustion:
    async def test_allows_up_to_capacity_then_blocks(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        for _ in range(5):
            decision = await limiter.check("k", capacity=5, refill_per_second=5 / 60)
            assert decision.allowed is True

        blocked = await limiter.check("k", capacity=5, refill_per_second=5 / 60)

        assert blocked.allowed is False

    async def test_a_capacity_of_one_allows_exactly_one_request(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        first = await limiter.check("k", capacity=1, refill_per_second=1 / 60)
        second = await limiter.check("k", capacity=1, refill_per_second=1 / 60)

        assert first.allowed is True
        assert second.allowed is False


class TestRetryAfterCorrectness:
    async def test_reflects_the_real_time_until_one_token_refills(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        capacity = 5
        refill_per_second = capacity / 60  # 5/minute
        for _ in range(capacity):
            await limiter.check("k", capacity=capacity, refill_per_second=refill_per_second)

        blocked = await limiter.check("k", capacity=capacity, refill_per_second=refill_per_second)

        # Exactly empty (0 tokens) -- needs a full 1/refill_per_second seconds for one token.
        assert blocked.retry_after_seconds == pytest.approx(12.0)

    async def test_a_zero_refill_rate_reports_infinite_retry_after(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        await limiter.check("k", capacity=1, refill_per_second=0)

        blocked = await limiter.check("k", capacity=1, refill_per_second=0)

        assert blocked.retry_after_seconds == float("inf")

    async def test_allowed_decisions_report_a_zero_retry_after(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        decision = await limiter.check("k", capacity=5, refill_per_second=5 / 60)

        assert decision.retry_after_seconds == 0.0


class TestRefillUsingTheInjectedClock:
    async def test_refills_gradually_as_time_advances(
        self, limiter: InMemoryTokenBucketRateLimiter, clock: _FakeClock
    ) -> None:
        capacity = 5
        refill_per_second = capacity / 60
        for _ in range(capacity):
            await limiter.check("k", capacity=capacity, refill_per_second=refill_per_second)
        assert (
            await limiter.check("k", capacity=capacity, refill_per_second=refill_per_second)
        ).allowed is False

        # Advance by exactly the time for one token to refill.
        clock.advance(12.0)

        decision = await limiter.check("k", capacity=capacity, refill_per_second=refill_per_second)
        assert decision.allowed is True
        # Immediately after, the bucket is empty again.
        assert (
            await limiter.check("k", capacity=capacity, refill_per_second=refill_per_second)
        ).allowed is False

    async def test_never_refills_past_capacity(
        self, limiter: InMemoryTokenBucketRateLimiter, clock: _FakeClock
    ) -> None:
        capacity = 5
        refill_per_second = capacity / 60
        await limiter.check("k", capacity=capacity, refill_per_second=refill_per_second)  # 4 left

        # Advance by far longer than needed to fully refill -- must cap at `capacity`, not
        # accumulate unbounded credit.
        clock.advance(3600.0)

        allowed_count = 0
        for _ in range(capacity + 1):
            if (
                await limiter.check("k", capacity=capacity, refill_per_second=refill_per_second)
            ).allowed:
                allowed_count += 1
        assert allowed_count == capacity

    async def test_a_fresh_key_starts_at_full_capacity(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        allowed_count = 0
        for _ in range(5):
            if (await limiter.check("brand-new-key", capacity=5, refill_per_second=5 / 60)).allowed:
                allowed_count += 1

        assert allowed_count == 5


class TestSeparateKeysDoNotInterfere:
    async def test_two_different_keys_have_independent_buckets(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        for _ in range(5):
            await limiter.check("ip:1.1.1.1", capacity=5, refill_per_second=5 / 60)
        exhausted = await limiter.check("ip:1.1.1.1", capacity=5, refill_per_second=5 / 60)
        other = await limiter.check("ip:2.2.2.2", capacity=5, refill_per_second=5 / 60)

        assert exhausted.allowed is False
        assert other.allowed is True

    async def test_different_scopes_for_the_same_identity_are_independent(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        """The same identity used in two different scopes (e.g. `general:ip:X` vs
        `login:ip:X`) must not share a bucket -- the scope is part of the key.
        """
        for _ in range(5):
            await limiter.check("login:ip:1.1.1.1", capacity=5, refill_per_second=5 / 60)
        login_exhausted = await limiter.check(
            "login:ip:1.1.1.1", capacity=5, refill_per_second=5 / 60
        )
        general_for_same_ip = await limiter.check(
            "general:ip:1.1.1.1", capacity=300, refill_per_second=300 / 60
        )

        assert login_exhausted.allowed is False
        assert general_for_same_ip.allowed is True


class TestConcurrentAccess:
    async def test_exactly_capacity_requests_succeed_under_concurrent_load(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        """20 concurrent callers, capacity 5 -- exactly 5 must succeed, never more (a race in
        the read-modify-write around `bucket.tokens` would allow more than `capacity`).
        """
        capacity = 5
        results = await asyncio.gather(
            *(
                limiter.check("shared-key", capacity=capacity, refill_per_second=capacity / 60)
                for _ in range(20)
            )
        )

        assert sum(1 for decision in results if decision.allowed) == capacity

    async def test_concurrent_access_to_different_keys_does_not_cross_contaminate(
        self, limiter: InMemoryTokenBucketRateLimiter
    ) -> None:
        async def consume_all(key: str) -> int:
            decisions = await asyncio.gather(
                *(limiter.check(key, capacity=3, refill_per_second=3 / 60) for _ in range(10))
            )
            return sum(1 for d in decisions if d.allowed)

        allowed_a, allowed_b = await asyncio.gather(consume_all("a"), consume_all("b"))

        assert allowed_a == 3
        assert allowed_b == 3


class TestNoOpRateLimiter:
    async def test_always_allows_regardless_of_capacity(self) -> None:
        limiter = NoOpRateLimiter()

        for _ in range(1000):
            decision = await limiter.check("any-key", capacity=1, refill_per_second=1 / 60)
            assert decision.allowed is True

    async def test_reports_a_zero_retry_after(self) -> None:
        limiter = NoOpRateLimiter()

        decision = await limiter.check("any-key", capacity=1, refill_per_second=1 / 60)

        assert decision.retry_after_seconds == 0.0
