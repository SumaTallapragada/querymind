"""Tests for `querymind.observability.models` — immutability and validation constraints."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from querymind.observability.models import (
    BenchmarkReport,
    BenchmarkResult,
    DiagnosticFinding,
    DiagnosticsReport,
    DiagnosticStatus,
    HealthCheck,
    HealthReport,
    HealthStatus,
    LogEvent,
    LogEventType,
    LogLevel,
    MetricsSnapshot,
    PipelineProfile,
    ProfilingStatistics,
    StageMetric,
    StructuredLogRecord,
)

_NOW = datetime(2026, 8, 6, tzinfo=UTC)


class TestLogEvent:
    def test_is_frozen(self) -> None:
        event = LogEvent(stage="nlu", event_type=LogEventType.STARTED, timestamp=_NOW)
        with pytest.raises(ValidationError):
            event.stage = "sql_execution"  # type: ignore[misc]

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            LogEvent(  # type: ignore[call-arg]
                stage="nlu", event_type=LogEventType.STARTED, timestamp=_NOW, unexpected="x"
            )

    def test_negative_duration_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LogEvent(
                stage="nlu",
                event_type=LogEventType.COMPLETED,
                timestamp=_NOW,
                duration_ms=-1.0,
            )


class TestStructuredLogRecord:
    def test_minimal_record_needs_only_level_message_timestamp(self) -> None:
        record = StructuredLogRecord(level=LogLevel.INFO, message="hello", timestamp=_NOW)
        assert record.stage is None
        assert record.correlation_id is None

    def test_is_frozen(self) -> None:
        record = StructuredLogRecord(level=LogLevel.INFO, message="hello", timestamp=_NOW)
        with pytest.raises(ValidationError):
            record.message = "changed"  # type: ignore[misc]


class TestStageMetric:
    def test_rejects_negative_counts(self) -> None:
        with pytest.raises(ValidationError):
            StageMetric(
                stage="nlu",
                call_count=-1,
                total_latency_ms=1.0,
                average_latency_ms=1.0,
                min_latency_ms=1.0,
                max_latency_ms=1.0,
            )


class TestMetricsSnapshot:
    def _snapshot(self, **overrides: object) -> MetricsSnapshot:
        defaults: dict[str, object] = {
            "captured_at": _NOW,
            "pipeline_run_count": 0,
            "pipeline_success_count": 0,
            "pipeline_failure_count": 0,
            "average_pipeline_latency_ms": 0.0,
            "validation_failure_count": 0,
            "repair_attempted_count": 0,
            "repair_success_count": 0,
            "repair_success_rate": 0.0,
            "sql_execution_count": 0,
            "total_rows_returned": 0,
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
            "cache_hit_count": 0,
            "cache_miss_count": 0,
        }
        defaults.update(overrides)
        return MetricsSnapshot(**defaults)  # type: ignore[arg-type]

    def test_stage_metrics_defaults_to_empty_tuple(self) -> None:
        snapshot = self._snapshot()
        assert snapshot.stage_metrics == ()

    def test_repair_success_rate_must_be_between_zero_and_one(self) -> None:
        with pytest.raises(ValidationError):
            self._snapshot(repair_success_rate=1.5)

    def test_is_frozen(self) -> None:
        snapshot = self._snapshot()
        with pytest.raises(ValidationError):
            snapshot.pipeline_run_count = 5  # type: ignore[misc]


class TestBenchmarkModels:
    def test_benchmark_result_rejects_zero_measured_iterations(self) -> None:
        with pytest.raises(ValidationError):
            BenchmarkResult(
                name="nlu",
                warmup_iterations=1,
                measured_iterations=0,
                average_ms=1.0,
                min_ms=1.0,
                max_ms=1.0,
                median_ms=1.0,
                p95_ms=1.0,
            )

    def test_benchmark_report_holds_a_tuple_of_results(self) -> None:
        result = BenchmarkResult(
            name="nlu",
            warmup_iterations=1,
            measured_iterations=5,
            average_ms=1.0,
            min_ms=0.5,
            max_ms=2.0,
            median_ms=1.0,
            p95_ms=1.9,
        )
        report = BenchmarkReport(results=(result,), generated_at=_NOW)
        assert report.results == (result,)


class TestDiagnosticModels:
    def test_diagnostics_report_holds_findings_and_overall_status(self) -> None:
        finding = DiagnosticFinding(
            check_name="metadata_registry", status=DiagnosticStatus.PASS, message="ok"
        )
        report = DiagnosticsReport(
            findings=(finding,), overall_status=DiagnosticStatus.PASS, generated_at=_NOW
        )
        assert report.findings == (finding,)
        assert report.overall_status is DiagnosticStatus.PASS


class TestHealthModels:
    def test_health_report_holds_checks_and_overall_status(self) -> None:
        check = HealthCheck(name="database_reachable", status=HealthStatus.HEALTHY)
        report = HealthReport(
            checks=(check,), overall_status=HealthStatus.HEALTHY, generated_at=_NOW
        )
        assert report.checks == (check,)


class TestProfilingModels:
    def test_percentage_of_total_must_be_at_most_100(self) -> None:
        with pytest.raises(ValidationError):
            ProfilingStatistics(
                stage="nlu", latency_ms=1.0, cumulative_latency_ms=1.0, percentage_of_total=101.0
            )

    def test_pipeline_profile_holds_stage_statistics(self) -> None:
        stat = ProfilingStatistics(
            stage="nlu", latency_ms=1.0, cumulative_latency_ms=1.0, percentage_of_total=100.0
        )
        profile = PipelineProfile(
            stage_statistics=(stat,),
            total_latency_ms=1.0,
            dominant_stage="nlu",
            dominant_stage_percentage=100.0,
            generated_at=_NOW,
        )
        assert profile.stage_statistics == (stat,)
