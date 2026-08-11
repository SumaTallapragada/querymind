"""Exceptions for `querymind.security` -- rate limiting today. Mirrors `querymind.auth
.exceptions`'s own shape: a plain exception, no HTTP awareness, mapping to a status code is
`querymind.api.exception_handlers`'s job.
"""

from __future__ import annotations


class RateLimitExceededError(Exception):
    """Raised when a caller has exhausted a `RateLimiter` bucket.

    Carries `retry_after_seconds` -- the *actual* time until that bucket can accept another
    request, computed from the bucket's own refill rate -- so
    `querymind.api.exception_handlers` can set a `Retry-After` header that reflects reality,
    never a hard-coded value. The message given to the constructor is what a client sees in the
    `detail` field, so it must stay generic (never a bucket key, capacity, or identity) -- see
    `querymind.api.dependencies`' rate-limit dependencies, which are the only callers.
    """

    def __init__(self, message: str, *, retry_after_seconds: float) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
