"""Security infrastructure (Phase 22D): audit logging and rate limiting -- concerns distinct
from `querymind.auth` (authentication: "who are you") and its own role-checking half
(authorization: "what are you allowed to do"). This package answers a third question: "how do
we detect abuse and reduce attack surface." It integrates with `querymind.auth` (an audit
event's `actor_user_id` references a real `User`; `AuditLog` shares `AuthBase`'s metadata)
rather than duplicating anything that package already owns -- no JWT/API-key logic, no role
comparison, lives here.
"""

from __future__ import annotations

from querymind.security.audit import AuditEventType, AuditLogger
from querymind.security.exceptions import RateLimitExceededError
from querymind.security.models import AuditLog
from querymind.security.rate_limiter import (
    InMemoryTokenBucketRateLimiter,
    NoOpRateLimiter,
    RateLimitDecision,
    RateLimiter,
)
from querymind.security.repository import AuditRepository

__all__ = [
    "AuditEventType",
    "AuditLog",
    "AuditLogger",
    "AuditRepository",
    "InMemoryTokenBucketRateLimiter",
    "NoOpRateLimiter",
    "RateLimitDecision",
    "RateLimitExceededError",
    "RateLimiter",
]
