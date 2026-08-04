"""Tests for `querymind.sql_generation.statistics.build_statistics`."""

from __future__ import annotations

import time

from querymind.sql_generation.models import ExtractionMethod
from querymind.sql_generation.statistics import build_statistics


class TestBuildStatistics:
    def test_captures_extraction_method(self) -> None:
        statistics = build_statistics(
            extraction_method=ExtractionMethod.FENCED_SQL_BLOCK,
            raw_sql="SELECT 1",
            normalized_sql="SELECT 1;",
            started=time.perf_counter(),
        )
        assert statistics.extraction_method is ExtractionMethod.FENCED_SQL_BLOCK

    def test_captures_raw_and_normalized_lengths(self) -> None:
        statistics = build_statistics(
            extraction_method=ExtractionMethod.RAW_TEXT,
            raw_sql="SELECT 1",
            normalized_sql="SELECT 1;",
            started=time.perf_counter(),
        )
        assert statistics.raw_sql_length == len("SELECT 1")
        assert statistics.normalized_sql_length == len("SELECT 1;")

    def test_flags_when_normalization_changed_the_sql(self) -> None:
        statistics = build_statistics(
            extraction_method=ExtractionMethod.RAW_TEXT,
            raw_sql="SELECT 1",
            normalized_sql="SELECT 1;",
            started=time.perf_counter(),
        )
        assert statistics.normalization_changed_sql is True

    def test_does_not_flag_when_normalization_was_a_no_op(self) -> None:
        statistics = build_statistics(
            extraction_method=ExtractionMethod.RAW_TEXT,
            raw_sql="SELECT 1;",
            normalized_sql="SELECT 1;",
            started=time.perf_counter(),
        )
        assert statistics.normalization_changed_sql is False

    def test_generation_latency_is_non_negative_and_reflects_elapsed_time(self) -> None:
        started = time.perf_counter()
        time.sleep(0.01)
        statistics = build_statistics(
            extraction_method=ExtractionMethod.RAW_TEXT,
            raw_sql="SELECT 1",
            normalized_sql="SELECT 1;",
            started=started,
        )
        assert statistics.generation_latency_ms >= 10.0
