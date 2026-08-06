"""Cache abstraction for recent streamed events -- defined, but deliberately not wired up.

Mirrors `querymind.orchestrator.cache`/`querymind.sql_execution.cache`/
`querymind.result_formatter.cache`'s reasoning exactly: a real
implementation of `EventReplayCache` (an in-memory ring buffer, most
likely) would let a client that briefly dropped its SSE/WebSocket
connection ask to replay events published for a `correlation_id` since
it last saw one -- a real feature, genuinely useful, and explicitly out
of scope for this phase (Phase 17 stops at "expose progress," not
"survive a reconnect"). `NoOpEventReplayCache` satisfies the protocol
without storing anything; nothing in this package calls it.
"""

from __future__ import annotations

from typing import Protocol

from querymind.streaming.models import PipelineEvent


class EventReplayCache(Protocol):
    """Interface for a short-lived buffer of recently published events, per correlation_id."""

    def append(self, correlation_id: str, event: PipelineEvent) -> None:
        """Record `event` as the most recent one published for `correlation_id`."""
        ...

    def recent(self, correlation_id: str) -> tuple[PipelineEvent, ...]:
        """Return every event buffered for `correlation_id` so far, oldest first."""
        ...

    def clear(self, correlation_id: str) -> None:
        """Discard every buffered event for `correlation_id`."""
        ...


class NoOpEventReplayCache:
    """An `EventReplayCache` that never buffers anything -- `recent` always returns `()`."""

    def append(self, correlation_id: str, event: PipelineEvent) -> None:
        return None

    def recent(self, correlation_id: str) -> tuple[PipelineEvent, ...]:
        return ()

    def clear(self, correlation_id: str) -> None:
        return None
