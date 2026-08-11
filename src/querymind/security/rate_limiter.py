"""Rate limiting -- a `RateLimiter` Protocol plus two implementations, mirroring
`querymind.auth.cache`'s own "Protocol + a real default + an explicit NoOp" shape exactly (that
module's own docstring applies the identical reasoning to a different risk: there, caching a
user lookup; here, sharing rate-limit state across more than one process).

`InMemoryTokenBucketRateLimiter` is correct for *this* deployment today -- `docker-compose.yml`
runs exactly one `app` replica, one uvicorn process, no `--workers N` -- so a per-process,
in-memory bucket genuinely reflects the *global* request state, not an approximation of it. It
stops being correct the moment this project ever runs more than one `app` process (horizontal
scaling, or `--workers N` on a single instance): each process would then enforce its own
independent bucket per key, silently multiplying the *effective* ceiling by however many
processes exist, since a caller's requests are no longer guaranteed to land on the same one.
Swapping in a shared-store-backed implementation (Redis, most likely) at that point requires
touching nothing else in this codebase: every call site here depends only on the `RateLimiter`
Protocol, never this class directly.

Token bucket, not fixed/sliding window: smooth refill (a burst doesn't get a free pass right at
a window boundary the way fixed-window can) and trivially deterministic to test with an
injectable clock -- mirrors `querymind.observability.logger.StructuredLogger`/
`StageInstrumentation`'s own "inject a clock, no real sleeping in tests" idiom.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The result of one `RateLimiter.check` call. Never raises for "no capacity left" -- the
    caller (a `querymind.api.dependencies` rate-limit dependency, or `querymind.streaming
    .websocket` directly) decides what that means, typically raising `RateLimitExceededError`.
    """

    allowed: bool
    retry_after_seconds: float = 0.0


class RateLimiter(Protocol):
    """Interface for a keyed rate limiter. `key` identifies one bucket -- callers compose it
    from a scope name and an identity (e.g. `"login:ip:203.0.113.5"`, `"query:user:42"`) so
    unrelated scopes/identities never share a bucket by accident; this Protocol has no opinion
    on key naming at all, only on the capacity/refill-rate/decision contract.
    """

    async def check(
        self, key: str, *, capacity: int, refill_per_second: float
    ) -> RateLimitDecision:
        """Attempt to consume one token from `key`'s bucket, creating it (full) on first use.

        `capacity` is the maximum burst a bucket ever holds; `refill_per_second` is how fast it
        refills once below capacity. Both are supplied on every call (not fixed at bucket
        creation) so a single limiter instance can back every scope in `Settings` at once,
        keyed only by the caller's own `key` string.
        """
        ...


@dataclass
class _Bucket:
    tokens: float
    last_refill: datetime


class InMemoryTokenBucketRateLimiter:
    """The real, shipped implementation -- see this module's own docstring for exactly which
    deployment shape it's correct for, and what breaks beyond it.

    `clock` is injectable (defaults to `datetime.now(UTC)`) so tests never need real sleeping,
    mirroring `StructuredLogger`/`StageInstrumentation`'s identical constructor-injected-clock
    idiom. A single `asyncio.Lock` guards every bucket read-modify-write: each one is a dict
    lookup plus float arithmetic, never I/O, so one lock for the whole limiter is not a
    meaningful contention point even under concurrent load -- and is simpler, and more obviously
    race-free, than a lock per key (which would itself need synchronized creation).
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def check(
        self, key: str, *, capacity: int, refill_per_second: float
    ) -> RateLimitDecision:
        async with self._lock:
            now = self._clock()
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(capacity), last_refill=now)
                self._buckets[key] = bucket
            else:
                elapsed = (now - bucket.last_refill).total_seconds()
                if elapsed > 0:
                    bucket.tokens = min(
                        float(capacity), bucket.tokens + elapsed * refill_per_second
                    )
                    bucket.last_refill = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return RateLimitDecision(allowed=True)

            missing = 1.0 - bucket.tokens
            retry_after = missing / refill_per_second if refill_per_second > 0 else float("inf")
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)


class NoOpRateLimiter:
    """Always allows -- backs `Settings.rate_limit_enabled=False`. Identical call shape to the
    real implementation, so disabling rate limiting changes zero call sites: every dependency in
    `querymind.api.dependencies` still calls `.check(...)` unconditionally either way, exercising
    the same structural code path in both configurations.
    """

    async def check(
        self, key: str, *, capacity: int, refill_per_second: float
    ) -> RateLimitDecision:
        return RateLimitDecision(allowed=True)
