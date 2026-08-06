"""Tests for `querymind.observability.logger` — `StructuredLogger` and `StageInstrumentation`."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pytest

from querymind.observability.logger import (
    InMemoryLogSink,
    StageInstrumentation,
    StdoutLogSink,
    StructuredLogger,
    generate_correlation_id,
)
from querymind.observability.models import LogEvent, LogEventType, LogLevel


class TestGenerateCorrelationId:
    def test_returns_a_non_empty_string(self) -> None:
        assert generate_correlation_id()

    def test_returns_a_different_id_each_call(self) -> None:
        assert generate_correlation_id() != generate_correlation_id()


class TestInMemoryLogSink:
    def test_write_appends_to_records(self) -> None:
        sink = InMemoryLogSink()
        logger = StructuredLogger(sink=sink)
        logger.info("hello")
        assert len(sink.records) == 1
        assert sink.records[0].message == "hello"

    def test_records_is_a_tuple(self) -> None:
        sink = InMemoryLogSink()
        assert isinstance(sink.records, tuple)


class TestStdoutLogSink:
    def test_writes_one_json_line_per_record(self) -> None:
        stream = io.StringIO()
        sink = StdoutLogSink(stream=stream)
        logger = StructuredLogger(sink=sink)
        logger.info("hello", stage="nlu")

        lines = stream.getvalue().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["message"] == "hello"
        assert parsed["stage"] == "nlu"


class TestStructuredLoggerLog:
    def test_default_sink_is_in_memory(self) -> None:
        logger = StructuredLogger()
        record = logger.info("hello")
        assert record.level is LogLevel.INFO
        assert record.message == "hello"

    def test_uses_the_injected_clock(self) -> None:
        fixed = datetime(2026, 8, 6, tzinfo=UTC)
        logger = StructuredLogger(clock=lambda: fixed)
        record = logger.info("hello")
        assert record.timestamp == fixed

    def test_error_populates_error_type_and_message(self) -> None:
        logger = StructuredLogger()
        record = logger.log(LogLevel.ERROR, "boom", error=ValueError("bad input"))
        assert record.error_type == "ValueError"
        assert record.error_message == "bad input"

    def test_debug_info_warning_error_use_the_right_level(self) -> None:
        logger = StructuredLogger()
        assert logger.debug("x").level is LogLevel.DEBUG
        assert logger.info("x").level is LogLevel.INFO
        assert logger.warning("x").level is LogLevel.WARNING
        assert logger.error("x").level is LogLevel.ERROR

    def test_every_field_is_passed_through(self) -> None:
        logger = StructuredLogger()
        record = logger.log(
            LogLevel.INFO,
            "hello",
            stage="nlu",
            event_type=LogEventType.STARTED,
            correlation_id="corr-1",
            request_id="req-1",
            duration_ms=12.5,
        )
        assert record.stage == "nlu"
        assert record.event_type is LogEventType.STARTED
        assert record.correlation_id == "corr-1"
        assert record.request_id == "req-1"
        assert record.duration_ms == 12.5


class TestStructuredLoggerEvent:
    def test_started_event_is_logged_at_info(self) -> None:
        logger = StructuredLogger()
        event = LogEvent(
            stage="nlu", event_type=LogEventType.STARTED, timestamp=datetime(2026, 8, 6, tzinfo=UTC)
        )
        record = logger.event(event)
        assert record.level is LogLevel.INFO
        assert record.stage == "nlu"

    def test_failed_event_is_logged_at_error(self) -> None:
        logger = StructuredLogger()
        event = LogEvent(
            stage="sql_execution",
            event_type=LogEventType.FAILED,
            timestamp=datetime(2026, 8, 6, tzinfo=UTC),
            error_type="RuntimeError",
            error_message="boom",
        )
        record = logger.event(event)
        assert record.level is LogLevel.ERROR
        assert record.error_type == "RuntimeError"

    def test_default_message_names_stage_and_event_type(self) -> None:
        logger = StructuredLogger()
        event = LogEvent(
            stage="nlu",
            event_type=LogEventType.COMPLETED,
            timestamp=datetime(2026, 8, 6, tzinfo=UTC),
        )
        record = logger.event(event)
        assert record.message == "nlu completed"

    def test_explicit_message_overrides_the_default(self) -> None:
        logger = StructuredLogger()
        event = LogEvent(
            stage="nlu",
            event_type=LogEventType.COMPLETED,
            timestamp=datetime(2026, 8, 6, tzinfo=UTC),
        )
        record = logger.event(event, message="custom message")
        assert record.message == "custom message"


class TestStageInstrumentation:
    def test_success_emits_started_then_completed(self) -> None:
        sink = InMemoryLogSink()
        logger = StructuredLogger(sink=sink)
        with StageInstrumentation(logger, "nlu"):
            pass
        assert [r.event_type for r in sink.records] == [
            LogEventType.STARTED,
            LogEventType.COMPLETED,
        ]

    def test_completed_record_has_a_non_negative_duration(self) -> None:
        sink = InMemoryLogSink()
        logger = StructuredLogger(sink=sink)
        with StageInstrumentation(logger, "nlu"):
            pass
        completed = sink.records[1]
        assert completed.duration_ms is not None
        assert completed.duration_ms >= 0.0

    def test_failure_emits_started_then_failed_and_reraises(self) -> None:
        sink = InMemoryLogSink()
        logger = StructuredLogger(sink=sink)
        with pytest.raises(ValueError, match="boom"), StageInstrumentation(logger, "sql_execution"):
            raise ValueError("boom")

        assert [r.event_type for r in sink.records] == [LogEventType.STARTED, LogEventType.FAILED]
        failed = sink.records[1]
        assert failed.error_type == "ValueError"
        assert failed.error_message == "boom"

    def test_correlation_and_request_id_are_carried_on_every_event(self) -> None:
        sink = InMemoryLogSink()
        logger = StructuredLogger(sink=sink)
        with StageInstrumentation(logger, "nlu", correlation_id="corr-1", request_id="req-1"):
            pass
        assert all(r.correlation_id == "corr-1" for r in sink.records)
        assert all(r.request_id == "req-1" for r in sink.records)

    def test_wrapped_code_never_needs_to_know_observability_exists(self) -> None:
        """The whole point of StageInstrumentation: instrument a call site, not the callee."""

        def parse(question: str) -> str:
            return question.upper()

        sink = InMemoryLogSink()
        logger = StructuredLogger(sink=sink)
        with StageInstrumentation(logger, "nlu"):
            result = parse("hello")

        assert result == "HELLO"
        assert len(sink.records) == 2
