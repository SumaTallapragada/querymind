"""Builds `SQLGenerationStatistics` from a generation run's intermediate artifacts.

A plain function, not a class — building statistics has no state of its
own to hold between calls, it only summarizes values `SQLGenerationEngine`
already computed during steps 1-4 of the pipeline.
"""

from __future__ import annotations

import time

from querymind.sql_generation.models import ExtractionMethod, SQLGenerationStatistics


def build_statistics(
    *, extraction_method: ExtractionMethod, raw_sql: str, normalized_sql: str, started: float
) -> SQLGenerationStatistics:
    """Build `SQLGenerationStatistics` for one run. `started` is a `time.perf_counter()` reading."""
    return SQLGenerationStatistics(
        extraction_method=extraction_method,
        raw_sql_length=len(raw_sql),
        normalized_sql_length=len(normalized_sql),
        normalization_changed_sql=raw_sql != normalized_sql,
        generation_latency_ms=(time.perf_counter() - started) * 1000,
    )
