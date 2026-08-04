"""Tests for `querymind.llm.retry`."""

from __future__ import annotations

import pytest

from querymind.llm.exceptions import (
    LLMConfigurationError,
    LLMPermanentError,
    LLMTransientError,
    RetryExhaustedError,
)
from querymind.llm.retry import RetryPolicy

from .conftest import RecordingSleep


class TestConstruction:
    def test_rejects_negative_max_retries(self) -> None:
        with pytest.raises(LLMConfigurationError):
            RetryPolicy(-1)

    def test_allows_zero_max_retries(self) -> None:
        policy = RetryPolicy(0)
        assert policy.max_retries == 0


class TestDelayForAttempt:
    def test_grows_exponentially(self) -> None:
        policy = RetryPolicy(5, base_delay_seconds=1.0, max_delay_seconds=1000.0)
        assert policy.delay_for_attempt(1) == 1.0
        assert policy.delay_for_attempt(2) == 2.0
        assert policy.delay_for_attempt(3) == 4.0
        assert policy.delay_for_attempt(4) == 8.0

    def test_caps_at_max_delay(self) -> None:
        policy = RetryPolicy(10, base_delay_seconds=1.0, max_delay_seconds=5.0)
        assert policy.delay_for_attempt(10) == 5.0


class TestExecuteSuccess:
    def test_succeeds_on_first_try_without_sleeping(self, no_sleep: RecordingSleep) -> None:
        policy = RetryPolicy(3, sleep=no_sleep)
        result, retry_count = policy.execute(lambda: "ok")
        assert result == "ok"
        assert retry_count == 0
        assert no_sleep.calls == []

    def test_succeeds_after_two_transient_failures(self, no_sleep: RecordingSleep) -> None:
        attempts = {"count": 0}

        def flaky() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise LLMTransientError("try again")
            return "ok"

        policy = RetryPolicy(5, sleep=no_sleep)
        result, retry_count = policy.execute(flaky)
        assert result == "ok"
        assert retry_count == 2
        assert len(no_sleep.calls) == 2

    def test_sleeps_with_exponentially_growing_delays(self, no_sleep: RecordingSleep) -> None:
        attempts = {"count": 0}

        def flaky() -> str:
            attempts["count"] += 1
            if attempts["count"] < 4:
                raise LLMTransientError("try again")
            return "ok"

        policy = RetryPolicy(5, base_delay_seconds=1.0, max_delay_seconds=1000.0, sleep=no_sleep)
        policy.execute(flaky)
        assert no_sleep.calls == [1.0, 2.0, 4.0]


class TestExecuteFailure:
    def test_raises_retry_exhausted_after_max_retries(self, no_sleep: RecordingSleep) -> None:
        def always_fails() -> str:
            raise LLMTransientError("always fails")

        policy = RetryPolicy(2, sleep=no_sleep)
        with pytest.raises(RetryExhaustedError) as exc_info:
            policy.execute(always_fails)
        assert exc_info.value.attempts == 3
        assert len(no_sleep.calls) == 2

    def test_non_transient_errors_are_never_retried(self, no_sleep: RecordingSleep) -> None:
        calls = {"count": 0}

        def fails_permanently() -> str:
            calls["count"] += 1
            raise LLMPermanentError("bad request")

        policy = RetryPolicy(3, sleep=no_sleep)
        with pytest.raises(LLMPermanentError):
            policy.execute(fails_permanently)
        assert calls["count"] == 1
        assert no_sleep.calls == []

    def test_zero_max_retries_tries_exactly_once(self, no_sleep: RecordingSleep) -> None:
        calls = {"count": 0}

        def always_fails() -> str:
            calls["count"] += 1
            raise LLMTransientError("fails")

        policy = RetryPolicy(0, sleep=no_sleep)
        with pytest.raises(RetryExhaustedError):
            policy.execute(always_fails)
        assert calls["count"] == 1
