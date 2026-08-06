"""Structured logging: a `Logger` Protocol, a default `StructuredLogger` implementation,
and `StageInstrumentation`, a context manager that emits started/completed/failed
`LogEvent`s around any block of code -- without that code needing to know
observability exists.

No logging backend is hardcoded anywhere in this module. `StructuredLogger`
writes every `StructuredLogRecord` it produces through an injected
`LogSink` -- `InMemoryLogSink` (the safe, side-effect-free default) or
`StdoutLogSink` (one JSON line per record, to an injected stream) are the
two provided implementations; a caller can supply any other `LogSink`
(e.g. one that forwards to `structlog`, used elsewhere in this project's
`core.logging` module -- deliberately not imported here, since this
package must stay usable with no framework at all).

`StageInstrumentation` is how a pipeline stage becomes observable "without
changing its behavior" (the mandatory rule this phase was built under):
wrap the *call site*, never the stage's own source --

    with StageInstrumentation(logger, "nlu", correlation_id=cid):
        query_context = parser.parse(question)

-- so `querymind.nlu` (or any other phase) never imports, calls, or even
knows this package exists.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, TextIO

from querymind.observability.models import (
    LogEvent,
    LogEventType,
    LogLevel,
    StructuredLogRecord,
)


def generate_correlation_id() -> str:
    """A convenience random correlation ID. Never required -- a caller may supply their own."""
    return uuid.uuid4().hex


class LogSink(Protocol):
    """Where a `StructuredLogRecord` ultimately goes. Injectable -- no backend hardcoded."""

    def write(self, record: StructuredLogRecord) -> None:
        """Persist or emit `record`. Must not raise for an ordinary write."""
        ...


class InMemoryLogSink:
    """Default `LogSink`: appends every record to an in-memory tuple. No I/O, no side effects.

    The safe default for `StructuredLogger` and for tests -- a caller who
    wants records to actually go anywhere (stdout, a file, a real logging
    framework) injects a different `LogSink` explicitly.
    """

    def __init__(self) -> None:
        self._records: list[StructuredLogRecord] = []

    def write(self, record: StructuredLogRecord) -> None:
        self._records.append(record)

    @property
    def records(self) -> tuple[StructuredLogRecord, ...]:
        """Every record written so far, in order."""
        return tuple(self._records)


class StdoutLogSink:
    """Writes each record as one JSON line to an injected stream (default `sys.stdout`).

    Uses the stream's own `.write`, never `print()`, per this package's
    "no print()" rule -- and writes exactly one JSON object per line
    (never string-concatenated free text), per its "structured logging
    only" rule.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def write(self, record: StructuredLogRecord) -> None:
        self._stream.write(record.model_dump_json() + "\n")


class Logger(Protocol):
    """Injectable structured-logging interface. Any conforming implementation may be substituted."""

    def log(
        self,
        level: LogLevel,
        message: str,
        *,
        stage: str | None = None,
        event_type: LogEventType | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
        duration_ms: float | None = None,
        error: BaseException | None = None,
    ) -> StructuredLogRecord:
        """Emit one structured log record and return it."""
        ...

    def event(self, event: LogEvent, message: str | None = None) -> StructuredLogRecord:
        """Emit a `LogEvent` as a `StructuredLogRecord`."""
        ...


class StructuredLogger:
    """The default `Logger` implementation. Builds a `StructuredLogRecord`, writes it via `LogSink`.

    Constructor-injected `sink` (default `InMemoryLogSink`) and `clock`
    (default `datetime.now(UTC)`) -- never a module-level logger instance,
    per this package's "no singleton loggers" rule; every caller
    constructs and owns its own `StructuredLogger`.
    """

    def __init__(
        self,
        sink: LogSink | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sink = sink if sink is not None else InMemoryLogSink()
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))

    def log(
        self,
        level: LogLevel,
        message: str,
        *,
        stage: str | None = None,
        event_type: LogEventType | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
        duration_ms: float | None = None,
        error: BaseException | None = None,
    ) -> StructuredLogRecord:
        record = StructuredLogRecord(
            level=level,
            message=message,
            timestamp=self._clock(),
            stage=stage,
            event_type=event_type,
            correlation_id=correlation_id,
            request_id=request_id,
            duration_ms=duration_ms,
            error_type=type(error).__name__ if error is not None else None,
            error_message=str(error) if error is not None else None,
        )
        self._sink.write(record)
        return record

    def event(self, event: LogEvent, message: str | None = None) -> StructuredLogRecord:
        level = LogLevel.ERROR if event.event_type is LogEventType.FAILED else LogLevel.INFO
        record = StructuredLogRecord(
            level=level,
            message=message or f"{event.stage} {event.event_type.value}",
            timestamp=event.timestamp,
            stage=event.stage,
            event_type=event.event_type,
            correlation_id=event.correlation_id,
            request_id=event.request_id,
            duration_ms=event.duration_ms,
            error_type=event.error_type,
            error_message=event.error_message,
        )
        self._sink.write(record)
        return record

    def debug(self, message: str, **fields: object) -> StructuredLogRecord:
        return self.log(LogLevel.DEBUG, message, **fields)  # type: ignore[arg-type]

    def info(self, message: str, **fields: object) -> StructuredLogRecord:
        return self.log(LogLevel.INFO, message, **fields)  # type: ignore[arg-type]

    def warning(self, message: str, **fields: object) -> StructuredLogRecord:
        return self.log(LogLevel.WARNING, message, **fields)  # type: ignore[arg-type]

    def error(self, message: str, **fields: object) -> StructuredLogRecord:
        return self.log(LogLevel.ERROR, message, **fields)  # type: ignore[arg-type]


class StageInstrumentation:
    """A context manager: emits STARTED on entry, COMPLETED or FAILED on exit, with duration.

    Wraps a call site, not a stage's own source -- the instrumented code
    never imports this package or changes in any way:

        with StageInstrumentation(logger, "nlu", correlation_id=cid):
            query_context = parser.parse(question)

    Re-raises whatever exception the wrapped block raised, after logging
    it as FAILED -- this is a passive observer, never a behavior change
    (it must not swallow an error the wrapped code itself would raise).
    """

    def __init__(
        self,
        logger: Logger,
        stage: str,
        *,
        correlation_id: str | None = None,
        request_id: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._logger = logger
        self._stage = stage
        self._correlation_id = correlation_id
        self._request_id = request_id
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        self._started_at: datetime | None = None

    def __enter__(self) -> StageInstrumentation:
        self._started_at = self._clock()
        self._logger.event(
            LogEvent(
                stage=self._stage,
                event_type=LogEventType.STARTED,
                timestamp=self._started_at,
                correlation_id=self._correlation_id,
                request_id=self._request_id,
            )
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        assert self._started_at is not None
        finished_at = self._clock()
        duration_ms = (finished_at - self._started_at).total_seconds() * 1000

        if exc is not None:
            self._logger.event(
                LogEvent(
                    stage=self._stage,
                    event_type=LogEventType.FAILED,
                    timestamp=finished_at,
                    correlation_id=self._correlation_id,
                    request_id=self._request_id,
                    duration_ms=duration_ms,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            return None

        self._logger.event(
            LogEvent(
                stage=self._stage,
                event_type=LogEventType.COMPLETED,
                timestamp=finished_at,
                correlation_id=self._correlation_id,
                request_id=self._request_id,
                duration_ms=duration_ms,
            )
        )
        return None
