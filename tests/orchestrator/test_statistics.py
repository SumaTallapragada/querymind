"""Tests for `querymind.orchestrator.statistics.PipelineStatisticsBuilder`."""

from __future__ import annotations

from querymind.orchestrator.models import PipelineStage, StageTiming
from querymind.orchestrator.statistics import PipelineStatisticsBuilder


class TestBuild:
    def test_assembles_every_field_verbatim(self) -> None:
        timings = (
            StageTiming(stage=PipelineStage.NLU, latency_ms=1.0),
            StageTiming(stage=PipelineStage.SCHEMA_LINKING, latency_ms=2.0),
        )
        stats = PipelineStatisticsBuilder().build(
            total_latency_ms=42.0,
            stage_timings=timings,
            repair_attempted=True,
            repair_performed=False,
        )
        assert stats.total_latency_ms == 42.0
        assert stats.stage_timings == timings
        assert stats.repair_attempted is True
        assert stats.repair_performed is False

    def test_no_stage_timings_is_valid(self) -> None:
        stats = PipelineStatisticsBuilder().build(
            total_latency_ms=5.0, stage_timings=(), repair_attempted=False, repair_performed=False
        )
        assert stats.stage_timings == ()
