"""Exponential-backoff retry policy for transient LLM provider failures.

`RetryPolicy` retries `querymind.llm.exceptions.LLMTransientError` only —
every other exception (a permanent failure, a parsing error, a
configuration error) propagates immediately, unretried. This is the one
place retry orchestration lives; providers themselves (see
`querymind.llm.providers`) never retry — they make exactly one call and
classify its outcome.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, TypeVar

from querymind.llm.exceptions import LLMConfigurationError, LLMTransientError, RetryExhaustedError

T = TypeVar("T")

#: Default base delay before the first retry, in seconds.
DEFAULT_BASE_DELAY_SECONDS = 0.5

#: Default ceiling on any single backoff delay, in seconds.
DEFAULT_MAX_DELAY_SECONDS = 30.0


class SleepFn(Protocol):
    """A `time.sleep`-shaped callable — injectable so tests never actually sleep."""

    def __call__(self, seconds: float) -> None: ...


def _default_sleep(seconds: float) -> None:
    """Wraps `time.sleep` with a signature matching `SleepFn` exactly (`time.sleep` also accepts
    `SupportsIndex`, which is a wider parameter type than `SleepFn` declares)."""
    time.sleep(seconds)


class RetryPolicy:
    """Retries an operation on `LLMTransientError`, waiting an exponentially growing delay each time."""

    def __init__(
        self,
        max_retries: int,
        *,
        base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
        max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
        sleep: SleepFn | None = None,
    ) -> None:
        if max_retries < 0:
            raise LLMConfigurationError(f"max_retries must be >= 0, got {max_retries!r}.")
        self._max_retries = max_retries
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds
        self._sleep: SleepFn = sleep if sleep is not None else _default_sleep

    @property
    def max_retries(self) -> int:
        return self._max_retries

    def delay_for_attempt(self, attempt: int) -> float:
        """Backoff delay before the `attempt`-th retry (1-indexed): `base * 2**(attempt-1)`, capped."""
        # `2.0 ** int` (a float base) is unambiguously float to mypy; `2 ** int` is not,
        # since a negative int exponent would make `int.__pow__` return something else.
        return min(self._base_delay_seconds * (2.0 ** (attempt - 1)), self._max_delay_seconds)

    def execute(self, operation: Callable[[], T]) -> tuple[T, int]:
        """Run `operation`, retrying on `LLMTransientError` up to `max_retries` times.

        Returns `(result, retry_count)`, where `retry_count` is how many
        retries were actually needed (0 means it succeeded on the first
        try). Raises `RetryExhaustedError` — wrapping the last transient
        error — if every attempt fails. Any exception other than
        `LLMTransientError` propagates immediately, unretried.
        """
        last_error: LLMTransientError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return operation(), attempt
            except LLMTransientError as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    break
                self._sleep(self.delay_for_attempt(attempt + 1))
        assert last_error is not None  # the loop always returns or sets last_error before breaking
        raise RetryExhaustedError(attempts=self._max_retries + 1, last_error=last_error)
