"""Maps engine-layer exceptions to deterministic HTTP responses. Never leaks a traceback.

Every handler here logs the exception (via the container's `Logger`,
never a bare `print()`) and returns a JSON `ErrorResponse` body -- the
same shape regardless of which exception was mapped, so a client can
always parse `detail`/`error_type` without knowing which phase raised.

`PipelineExecutionError` is handled specially: the *original* stage
failure it wraps (`exc.__cause__`) is what actually determines the
status code and message -- a caller of `/query/sql` shouldn't see
"PipelineExecutionError" as the reported error type when the real cause
was, say, an unreachable database.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from querymind.api.models.response import ErrorResponse
from querymind.auth.exceptions import (
    DuplicateUserError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)
from querymind.nlu import EmptyQuestionError
from querymind.observability.exceptions import ObservabilityConfigurationError
from querymind.orchestrator.exceptions import PipelineConfigurationError, PipelineExecutionError
from querymind.result_formatter import FormattingError
from querymind.sql_execution import (
    DatabaseConnectionError,
    ExecutionRejectedError,
    ExecutionTimeoutError,
    SQLExecutionConfigurationError,
)
from querymind.sql_repair import SQLRepairConfigurationError

#: (exception type, HTTP status code) pairs, most specific first -- checked in order, so a
#: subclass listed before its parent always wins. Anything not listed here falls back to 500.
#: The six `querymind.auth.exceptions` entries are Phase 22A Part 2's only addition here --
#: every one of them is already raised by `AuthenticationService` (Part 1, unchanged); this is
#: just where every other engine's exceptions already get mapped to a status code too.
_STATUS_BY_EXCEPTION: tuple[tuple[type[Exception], int], ...] = (
    (EmptyQuestionError, status.HTTP_400_BAD_REQUEST),
    (ExecutionRejectedError, status.HTTP_400_BAD_REQUEST),
    (FormattingError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (ExecutionTimeoutError, status.HTTP_504_GATEWAY_TIMEOUT),
    (DatabaseConnectionError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (PipelineConfigurationError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (SQLExecutionConfigurationError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (SQLRepairConfigurationError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (ObservabilityConfigurationError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (DuplicateUserError, status.HTTP_409_CONFLICT),
    (InvalidCredentialsError, status.HTTP_401_UNAUTHORIZED),
    (InvalidTokenError, status.HTTP_401_UNAUTHORIZED),
    (TokenExpiredError, status.HTTP_401_UNAUTHORIZED),
    (RefreshTokenRevokedError, status.HTTP_401_UNAUTHORIZED),
    (InactiveUserError, status.HTTP_403_FORBIDDEN),
)


def _status_for(exc: BaseException) -> int:
    for exc_type, code in _STATUS_BY_EXCEPTION:
        if isinstance(exc, exc_type):
            return code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _log_and_respond(
    request: Request, *, status_code: int, message: str, error_type: str
) -> JSONResponse:
    logger = request.app.state.container.logger
    logger.error(message, request_id=request.headers.get("X-Request-ID"))
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(detail=message, error_type=error_type).model_dump(),
    )


async def _handle_mapped_exception(request: Request, exc: Exception) -> JSONResponse:
    return _log_and_respond(
        request,
        status_code=_status_for(exc),
        message=str(exc),
        error_type=type(exc).__name__,
    )


async def _handle_pipeline_execution_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, PipelineExecutionError)
    cause = exc.__cause__
    if cause is not None:
        return _log_and_respond(
            request,
            status_code=_status_for(cause),
            message=str(cause),
            error_type=type(cause).__name__,
        )
    return _log_and_respond(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=str(exc),
        error_type=type(exc).__name__,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every mapped exception handler. Does not touch the generic `Exception` handler
    (`querymind.api.app` keeps that one, unchanged from Phase 1, as the final safety net).
    """
    for exc_type, _ in _STATUS_BY_EXCEPTION:
        app.add_exception_handler(exc_type, _handle_mapped_exception)
    app.add_exception_handler(PipelineExecutionError, _handle_pipeline_execution_error)
