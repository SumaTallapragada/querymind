"""Structured logging configuration.

Uses ``structlog`` layered on top of the standard library ``logging``
module so that:

* Every log line — whether emitted by our code, Uvicorn, or a third-party
  library using stdlib ``logging`` — goes through the same processor
  pipeline and comes out in the same shape.
* In production (``LOG_FORMAT=json``) logs are single-line JSON, ready for
  a log aggregator (CloudWatch, Datadog, Loki, ...).
* In development (``LOG_FORMAT=console``) logs are colorized and
  human-readable.
* Request-scoped context (e.g. a request ID) can be bound once per request
  and automatically attached to every subsequent log line for that
  request, via ``structlog.contextvars``.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog

from querymind.core.config import LogFormat


def configure_logging(*, log_level: str, log_format: LogFormat) -> None:
    """Configure stdlib ``logging`` and ``structlog`` for the process.

    Must be called once, as early as possible during application startup,
    before any logger is instantiated.
    """
    level = logging.getLevelName(log_level.upper())

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # Route Uvicorn's own loggers through the same handler/formatter so
    # access logs and our application logs are visually and structurally
    # consistent.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


def get_logger(**initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger, optionally pre-bound with context."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(**initial_values))
