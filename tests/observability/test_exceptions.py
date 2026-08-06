"""Tests for `querymind.observability.exceptions` — the exception hierarchy."""

from __future__ import annotations

import pytest

from querymind.observability.exceptions import (
    BenchmarkError,
    LoggingError,
    MetricsError,
    ObservabilityConfigurationError,
    ObservabilityError,
    ProfilingError,
)


@pytest.mark.parametrize(
    "exception_class",
    [
        ObservabilityConfigurationError,
        LoggingError,
        MetricsError,
        BenchmarkError,
        ProfilingError,
    ],
)
class TestHierarchy:
    def test_is_an_observability_error(self, exception_class: type[Exception]) -> None:
        assert issubclass(exception_class, ObservabilityError)

    def test_is_a_plain_exception(self, exception_class: type[Exception]) -> None:
        assert issubclass(exception_class, Exception)

    def test_carries_its_message(self, exception_class: type[Exception]) -> None:
        error = exception_class("something went wrong")
        assert str(error) == "something went wrong"


class TestObservabilityErrorItself:
    def test_is_a_plain_exception(self) -> None:
        assert issubclass(ObservabilityError, Exception)
