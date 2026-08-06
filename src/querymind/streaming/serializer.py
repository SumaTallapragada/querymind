"""Wire-format serialization for `PipelineEvent`, shared by both transports.

One function, `serialize_event`, is the entire seam: `querymind.streaming.sse`
wraps its result in SSE framing (`event: <type>\\ndata: <json>\\n\\n`) and
`.websocket` sends it as one WebSocket text frame, unwrapped -- but
neither transport module reaches into a `PipelineEvent`'s fields itself,
so the JSON shape only ever needs to change in this one place.
"""

from __future__ import annotations

from querymind.streaming.models import PipelineEvent


def serialize_event(event: PipelineEvent) -> str:
    """Render `event` as one compact JSON string -- Pydantic's own `model_dump_json`, which
    already handles `datetime`/`Enum` encoding consistently with every other model in this
    project (`StructuredLogRecord.model_dump_json`, used by `StdoutLogSink`, is the precedent).
    """
    return event.model_dump_json()
