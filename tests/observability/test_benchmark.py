"""Tests for `querymind.observability.benchmark.BenchmarkRunner`."""

from __future__ import annotations

import itertools
from collections.abc import Callable

import pytest

from querymind.observability.benchmark import BenchmarkRunner
from querymind.observability.exceptions import BenchmarkError
from querymind.observability.models import BenchmarkReport


def _fake_clock(values: list[float]) -> Callable[[], float]:
    iterator = iter(values)

    def clock() -> float:
        return next(iterator)

    return clock


class TestConstruction:
    def test_negative_warmup_iterations_is_rejected(self) -> None:
        with pytest.raises(BenchmarkError):
            BenchmarkRunner(warmup_iterations=-1)

    def test_zero_measured_iterations_is_rejected(self) -> None:
        with pytest.raises(BenchmarkError):
            BenchmarkRunner(measured_iterations=0)

    def test_zero_warmup_iterations_is_valid(self) -> None:
        BenchmarkRunner(warmup_iterations=0)


class TestRun:
    def test_calls_fn_warmup_plus_measured_times(self) -> None:
        calls = 0

        def fn() -> None:
            nonlocal calls
            calls += 1

        runner = BenchmarkRunner(warmup_iterations=2, measured_iterations=3)
        runner.run("noop", fn)
        assert calls == 5

    def test_result_reports_the_given_name_and_iteration_counts(self) -> None:
        runner = BenchmarkRunner(warmup_iterations=1, measured_iterations=4)
        result = runner.run("noop", lambda: None)
        assert result.name == "noop"
        assert result.warmup_iterations == 1
        assert result.measured_iterations == 4

    def test_per_call_overrides_take_priority_over_constructor_defaults(self) -> None:
        calls = 0

        def fn() -> None:
            nonlocal calls
            calls += 1

        runner = BenchmarkRunner(warmup_iterations=1, measured_iterations=1)
        runner.run("noop", fn, warmup_iterations=0, measured_iterations=3)
        assert calls == 3

    def test_deterministic_durations_produce_exact_statistics(self) -> None:
        # Clock returns pairs of (start, end) per measured iteration: durations 10, 20, 30 ms.
        clock_values = itertools.chain.from_iterable(
            [(0.000, 0.010), (0.010, 0.030), (0.030, 0.060)]
        )
        runner = BenchmarkRunner(
            warmup_iterations=0, measured_iterations=3, clock=_fake_clock(list(clock_values))
        )
        result = runner.run("fixed", lambda: None)
        assert result.min_ms == pytest.approx(10.0)
        assert result.max_ms == pytest.approx(30.0)
        assert result.median_ms == pytest.approx(20.0)
        assert result.average_ms == pytest.approx(20.0)

    def test_single_measured_iteration_is_valid(self) -> None:
        runner = BenchmarkRunner(warmup_iterations=0, measured_iterations=1)
        result = runner.run("noop", lambda: None)
        assert result.measured_iterations == 1
        assert result.min_ms == result.max_ms == result.median_ms == result.p95_ms


class TestRunAsync:
    async def test_calls_fn_warmup_plus_measured_times(self) -> None:
        calls = 0

        async def fn() -> None:
            nonlocal calls
            calls += 1

        runner = BenchmarkRunner(warmup_iterations=1, measured_iterations=2)
        await runner.run_async("noop", fn)
        assert calls == 3

    async def test_result_shape_matches_the_sync_path(self) -> None:
        async def fn() -> None:
            return None

        runner = BenchmarkRunner(warmup_iterations=0, measured_iterations=2)
        result = await runner.run_async("noop", fn)
        assert result.name == "noop"
        assert result.measured_iterations == 2


class TestReport:
    def test_assembles_every_result_into_one_report(self) -> None:
        runner = BenchmarkRunner(warmup_iterations=0, measured_iterations=1)
        first = runner.run("a", lambda: None)
        second = runner.run("b", lambda: None)
        report = BenchmarkRunner.report((first, second))
        assert isinstance(report, BenchmarkReport)
        assert report.results == (first, second)
