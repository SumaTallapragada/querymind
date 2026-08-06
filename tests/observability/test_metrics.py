"""Tests for `querymind.observability.metrics.InMemoryMetricsCollector`."""

from __future__ import annotations

from datetime import UTC, datetime

from querymind.observability.metrics import InMemoryMetricsCollector


class TestPipelineRuns:
    def test_counts_successes_and_failures_separately(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_pipeline_run(
            success=True, latency_ms=100.0, repair_attempted=False, repair_succeeded=False
        )
        collector.record_pipeline_run(
            success=False, latency_ms=50.0, repair_attempted=False, repair_succeeded=False
        )
        snapshot = collector.snapshot()
        assert snapshot.pipeline_run_count == 2
        assert snapshot.pipeline_success_count == 1
        assert snapshot.pipeline_failure_count == 1

    def test_average_latency_is_computed_across_all_runs(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_pipeline_run(
            success=True, latency_ms=100.0, repair_attempted=False, repair_succeeded=False
        )
        collector.record_pipeline_run(
            success=True, latency_ms=200.0, repair_attempted=False, repair_succeeded=False
        )
        assert collector.snapshot().average_pipeline_latency_ms == 150.0

    def test_zero_runs_has_zero_average_latency_not_a_division_error(self) -> None:
        collector = InMemoryMetricsCollector()
        assert collector.snapshot().average_pipeline_latency_ms == 0.0


class TestRepairMetrics:
    def test_repair_success_rate_is_success_over_attempted(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_pipeline_run(
            success=True, latency_ms=1.0, repair_attempted=True, repair_succeeded=True
        )
        collector.record_pipeline_run(
            success=False, latency_ms=1.0, repair_attempted=True, repair_succeeded=False
        )
        snapshot = collector.snapshot()
        assert snapshot.repair_attempted_count == 2
        assert snapshot.repair_success_count == 1
        assert snapshot.repair_success_rate == 0.5

    def test_repair_success_rate_is_zero_when_repair_never_attempted(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_pipeline_run(
            success=True, latency_ms=1.0, repair_attempted=False, repair_succeeded=False
        )
        assert collector.snapshot().repair_success_rate == 0.0

    def test_repair_succeeded_is_ignored_when_not_attempted(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_pipeline_run(
            success=True, latency_ms=1.0, repair_attempted=False, repair_succeeded=True
        )
        snapshot = collector.snapshot()
        assert snapshot.repair_attempted_count == 0
        assert snapshot.repair_success_count == 0


class TestStageLatency:
    def test_stage_metrics_reports_count_and_average(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_stage_latency("nlu", 10.0)
        collector.record_stage_latency("nlu", 20.0)
        collector.record_stage_latency("schema_linking", 5.0)

        snapshot = collector.snapshot()
        by_stage = {m.stage: m for m in snapshot.stage_metrics}
        assert by_stage["nlu"].call_count == 2
        assert by_stage["nlu"].average_latency_ms == 15.0
        assert by_stage["nlu"].min_latency_ms == 10.0
        assert by_stage["nlu"].max_latency_ms == 20.0
        assert by_stage["schema_linking"].call_count == 1

    def test_no_stage_latency_recorded_means_an_empty_tuple(self) -> None:
        collector = InMemoryMetricsCollector()
        assert collector.snapshot().stage_metrics == ()


class TestValidationExecutionAndLLMMetrics:
    def test_validation_failure_count_accumulates(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_validation_failure()
        collector.record_validation_failure()
        assert collector.snapshot().validation_failure_count == 2

    def test_sql_execution_count_and_rows_returned_accumulate(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_sql_execution(rows_returned=5)
        collector.record_sql_execution(rows_returned=10)
        snapshot = collector.snapshot()
        assert snapshot.sql_execution_count == 2
        assert snapshot.total_rows_returned == 15

    def test_llm_token_usage_accumulates(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_llm_token_usage(prompt_tokens=100, completion_tokens=20)
        collector.record_llm_token_usage(prompt_tokens=50, completion_tokens=10)
        snapshot = collector.snapshot()
        assert snapshot.llm_prompt_tokens == 150
        assert snapshot.llm_completion_tokens == 30


class TestCacheMetrics:
    def test_hit_and_miss_are_counted_separately(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_cache_access(hit=True)
        collector.record_cache_access(hit=True)
        collector.record_cache_access(hit=False)
        snapshot = collector.snapshot()
        assert snapshot.cache_hit_count == 2
        assert snapshot.cache_miss_count == 1


class TestStartupTime:
    def test_defaults_to_none(self) -> None:
        collector = InMemoryMetricsCollector()
        assert collector.snapshot().startup_time_ms is None

    def test_records_the_last_recorded_value(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_startup_time(500.0)
        assert collector.snapshot().startup_time_ms == 500.0


class TestSnapshotIndependence:
    def test_a_snapshot_is_not_updated_by_later_recordings(self) -> None:
        collector = InMemoryMetricsCollector()
        collector.record_validation_failure()
        first = collector.snapshot()
        collector.record_validation_failure()
        second = collector.snapshot()

        assert first.validation_failure_count == 1
        assert second.validation_failure_count == 2

    def test_uses_the_injected_clock(self) -> None:
        fixed = datetime(2026, 8, 6, tzinfo=UTC)
        collector = InMemoryMetricsCollector(clock=lambda: fixed)
        assert collector.snapshot().captured_at == fixed

    def test_two_independent_collectors_do_not_share_state(self) -> None:
        first = InMemoryMetricsCollector()
        second = InMemoryMetricsCollector()
        first.record_validation_failure()
        assert first.snapshot().validation_failure_count == 1
        assert second.snapshot().validation_failure_count == 0
