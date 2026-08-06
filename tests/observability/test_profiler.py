"""Tests for `querymind.observability.profiler.PipelineProfiler`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from querymind.observability.exceptions import ProfilingError
from querymind.observability.profiler import PipelineProfiler


class TestProfile:
    def test_empty_input_raises_profiling_error(self) -> None:
        with pytest.raises(ProfilingError):
            PipelineProfiler().profile([])

    def test_single_stage_is_100_percent_and_dominant(self) -> None:
        profile = PipelineProfiler().profile([("nlu", 10.0)])
        assert profile.total_latency_ms == 10.0
        assert profile.dominant_stage == "nlu"
        assert profile.dominant_stage_percentage == pytest.approx(100.0)
        assert profile.stage_statistics[0].percentage_of_total == pytest.approx(100.0)

    def test_percentages_sum_to_100(self) -> None:
        profile = PipelineProfiler().profile([("a", 10.0), ("b", 30.0), ("c", 60.0)])
        total_percentage = sum(s.percentage_of_total for s in profile.stage_statistics)
        assert total_percentage == pytest.approx(100.0)

    def test_dominant_stage_is_the_one_with_highest_latency(self) -> None:
        profile = PipelineProfiler().profile([("a", 10.0), ("b", 90.0), ("c", 5.0)])
        assert profile.dominant_stage == "b"
        assert profile.dominant_stage_percentage == pytest.approx(90.0 / 105.0 * 100)

    def test_cumulative_latency_accumulates_in_input_order(self) -> None:
        profile = PipelineProfiler().profile([("a", 10.0), ("b", 20.0), ("c", 30.0)])
        cumulative = [s.cumulative_latency_ms for s in profile.stage_statistics]
        assert cumulative == pytest.approx([10.0, 30.0, 60.0])

    def test_stage_order_is_preserved(self) -> None:
        profile = PipelineProfiler().profile([("z", 1.0), ("a", 2.0), ("m", 3.0)])
        assert [s.stage for s in profile.stage_statistics] == ["z", "a", "m"]

    def test_total_latency_is_the_sum_of_every_stage(self) -> None:
        profile = PipelineProfiler().profile([("a", 1.5), ("b", 2.5)])
        assert profile.total_latency_ms == pytest.approx(4.0)

    def test_uses_the_injected_clock(self) -> None:
        fixed = datetime(2026, 8, 6, tzinfo=UTC)
        profile = PipelineProfiler(clock=lambda: fixed).profile([("a", 1.0)])
        assert profile.generated_at == fixed

    def test_zero_total_latency_does_not_divide_by_zero(self) -> None:
        profile = PipelineProfiler().profile([("a", 0.0), ("b", 0.0)])
        assert all(s.percentage_of_total == 0.0 for s in profile.stage_statistics)
