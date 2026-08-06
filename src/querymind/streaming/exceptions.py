"""Domain-specific exceptions for the Streaming presentation layer.

None of these describe a pipeline failure -- a failing pipeline stage is
reported as a `StageFailedEvent`/`PipelineFailedEvent`, never raised here;
see `querymind.streaming.models`. Everything below is instead a failure
of the *transport* itself: a malformed inbound message, a bus that was
asked to publish to a topic nobody ever subscribed to, or a caller
misconfiguring a collaborator.
"""

from __future__ import annotations


class StreamingError(Exception):
    """Base class for every exception raised within `querymind.streaming`."""


class StreamingConfigurationError(StreamingError):
    """Raised when a `querymind.streaming` component is constructed with invalid collaborators."""


class InvalidStreamRequestError(StreamingError):
    """Raised when an inbound SSE/WebSocket request cannot be parsed into a valid question.

    Mirrors `querymind.nlu.EmptyQuestionError`'s role one layer up: a
    malformed or empty `{"question": ...}` payload is a client error
    (SSE: `422`; WebSocket: closed with a policy-violation code), never a
    pipeline failure.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class UnknownSubscriptionError(StreamingError):
    """Raised by `EventBus.unsubscribe` when given a subscription it never issued."""
