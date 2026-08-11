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

Phase 22D also audits the *failure* half of login/registration/refresh (success is audited
inline in `querymind.api.routers.auth`, the only place that can observe it) and every
authorization denial, from exactly here -- this is the one place that already sees every mapped
exception for every route, so no per-route change is needed for the failure side at all. Audit
logging is best-effort and wrapped so it can never turn an already-in-flight error response into
a different (or worse, a 500) one; see `_audit_failure_if_relevant`'s own docstring.

`RateLimitExceededError` (Phase 22D) gets its own dedicated handler, mirroring
`PipelineExecutionError`'s own precedent -- see `_handle_rate_limit_exceeded`'s own docstring.
"""

from __future__ import annotations

from math import ceil
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from querymind.api.client_info import get_client_ip, get_user_agent
from querymind.api.models.response import ErrorResponse
from querymind.auth.exceptions import (
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyRevokedError,
    DuplicateUserError,
    ForbiddenRoleError,
    InactiveUserError,
    InsufficientPermissionsError,
    InvalidApiKeyError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)
from querymind.core.config import Settings
from querymind.nlu import EmptyQuestionError
from querymind.observability.exceptions import ObservabilityConfigurationError
from querymind.orchestrator.exceptions import PipelineConfigurationError, PipelineExecutionError
from querymind.result_formatter import FormattingError
from querymind.security.audit import AuditEventType
from querymind.security.exceptions import RateLimitExceededError
from querymind.sql_execution import (
    DatabaseConnectionError,
    ExecutionRejectedError,
    ExecutionTimeoutError,
    SQLExecutionConfigurationError,
)
from querymind.sql_repair import SQLRepairConfigurationError

#: (exception type, HTTP status code) pairs, most specific first -- checked in order, so a
#: subclass listed before its parent always wins. Anything not listed here falls back to 500.
#: The `querymind.auth.exceptions` entries are Phase 22A Part 2's (six `AuthenticationError`
#: subclasses), Phase 22B's (two `AuthorizationError` subclasses, both 403 -- authorization
#: failures are never 401: the caller *is* authenticated, `CurrentUser` already succeeded,
#: they're just not permitted to do this one thing), and Phase 22D's four API-key exceptions
#: (three 401s mirroring the JWT trio's shape, plus `ApiKeyNotFoundError` at 404 for a
#: revoke-by-id that doesn't exist or isn't the caller's) -- every one of them is already raised
#: by `AuthenticationService`; this is just where every other engine's exceptions already get
#: mapped to a status code too.
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
    (InvalidApiKeyError, status.HTTP_401_UNAUTHORIZED),
    (ApiKeyExpiredError, status.HTTP_401_UNAUTHORIZED),
    (ApiKeyRevokedError, status.HTTP_401_UNAUTHORIZED),
    (ApiKeyNotFoundError, status.HTTP_404_NOT_FOUND),
    (InactiveUserError, status.HTTP_403_FORBIDDEN),
    (ForbiddenRoleError, status.HTTP_403_FORBIDDEN),
    (InsufficientPermissionsError, status.HTTP_403_FORBIDDEN),
)


#: Field names FastAPI's default `RequestValidationError` handler must never echo back in a
#: `422` body's `input` key (Phase 22D-5 finding: Pydantic v2 includes the exact submitted value
#: for every failed field, e.g. `{"loc": ["body", "password"], "input": "the-actual-password", ...}`
#: -- harmless for `username`/`email`/`question`/etc., but a real secret for these. Matched
#: case-insensitively against a `loc` tuple's *last* segment (the field name itself), so this
#: still fires however deeply nested the field is. `_handle_validation_error` below is the one
#: place this list is applied -- see its own docstring for why the whole response isn't stripped.
_SENSITIVE_FIELD_NAMES = frozenset(
    {"password", "refresh_token", "access_token", "raw_key", "api_key", "authorization"}
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


#: Maps a route's path *suffix* (not the full path, so this is indifferent to whatever
#: `Settings.api_v1_prefix` is configured to) to the audit event a failure there represents.
_AUTH_FAILURE_EVENT_BY_PATH_SUFFIX: tuple[tuple[str, AuditEventType], ...] = (
    ("/auth/login", AuditEventType.LOGIN_FAILURE),
    ("/auth/register", AuditEventType.REGISTRATION_FAILURE),
    ("/auth/refresh", AuditEventType.REFRESH_FAILURE),
)


async def _attempted_username(request: Request) -> str | None:
    """Best-effort: `UserLogin`/`UserCreate` both have a `username` field; a bare refresh
    request body doesn't, so this naturally returns `None` there. Never raises -- an
    unparsable/already-consumed body just means no username is recorded, not a broken response.
    """
    try:
        body = await request.json()
    except Exception:
        return None
    username = body.get("username") if isinstance(body, dict) else None
    return username if isinstance(username, str) else None


async def _audit_failure_if_relevant(request: Request, exc: Exception) -> None:
    """The failure-side half of Phase 22D's audit logging -- see this module's own docstring for
    why it lives here rather than in each route. Deliberately swallows every exception of its
    own: a bug in audit logging must never change (or break) the error response a client
    already-legitimately-failing request was about to receive.
    """
    try:
        container = getattr(request.app.state, "container", None)
        if container is None:
            return
        settings: Settings = request.app.state.settings
        common = {
            "ip_address": get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers),
            "user_agent": get_user_agent(request),
            "request_id": getattr(request.state, "request_id", None),
            "correlation_id": getattr(request.state, "correlation_id", None),
            "resource": request.url.path,
            "metadata": {"error_type": type(exc).__name__},
        }

        if isinstance(exc, ForbiddenRoleError | InsufficientPermissionsError):
            user = getattr(request.state, "user", None)
            await container.audit_logger.record(
                AuditEventType.AUTHORIZATION_DENIED,
                success=False,
                actor_user_id=user.id if user is not None else None,
                actor_username=user.username if user is not None else None,
                **common,
            )
            return

        path = request.url.path
        for suffix, event_type in _AUTH_FAILURE_EVENT_BY_PATH_SUFFIX:
            if path.endswith(suffix):
                await container.audit_logger.record(
                    event_type,
                    success=False,
                    actor_username=await _attempted_username(request),
                    **common,
                )
                return
    except Exception:
        return


async def _handle_mapped_exception(request: Request, exc: Exception) -> JSONResponse:
    await _audit_failure_if_relevant(request, exc)
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


async def _handle_rate_limit_exceeded(request: Request, exc: Exception) -> JSONResponse:
    """`RateLimitExceededError` gets its own handler, not a `_STATUS_BY_EXCEPTION` entry --
    mirrors `PipelineExecutionError`'s own precedent for the same reason: it needs to do
    something no other mapped exception does (attach a `Retry-After` header carrying the
    exception's own `retry_after_seconds`, computed from the bucket's real refill rate, never a
    hard-coded value -- see `RateLimitExceededError`'s own docstring). `ceil` + a `max(1, ...)`
    floor: `Retry-After` is conventionally a whole number of seconds, and telling a client to
    retry in `0` seconds is a meaningless signal.
    """
    assert isinstance(exc, RateLimitExceededError)
    response = _log_and_respond(
        request,
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        message=str(exc),
        error_type=type(exc).__name__,
    )
    response.headers["Retry-After"] = str(max(1, ceil(exc.retry_after_seconds)))
    return response


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """The same `422` shape FastAPI's own default `RequestValidationError` handler returns
    (`{"detail": [...]}`, one entry per failed field, run through the same `jsonable_encoder`),
    minus one thing: an entry whose field name is in `_SENSITIVE_FIELD_NAMES` has its `input` key
    removed before encoding.

    Without this, a real (just too-short, or wrong-typed) password/refresh-token/API-key a
    caller actually submitted comes back verbatim in the `422` body -- Pydantic v2 includes the
    exact submitted value for every failed field by design, which is genuinely useful for an
    ordinary field (`username`, `email`, `question`) but never acceptable for a credential; see
    this module's own `_SENSITIVE_FIELD_NAMES` docstring. Every other part of the error (its
    `type`/`loc`/`msg`/`ctx`) is left exactly as FastAPI would have returned it -- a caller still
    learns *which* field failed and *why*, just not the secret value it rejected.
    """
    assert isinstance(exc, RequestValidationError)
    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        if loc and str(loc[-1]).lower() in _SENSITIVE_FIELD_NAMES:
            error = {key: value for key, value in error.items() if key != "input"}
        errors.append(error)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(errors)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every mapped exception handler. Does not touch the generic `Exception` handler
    (`querymind.api.app` keeps that one, unchanged from Phase 1, as the final safety net).
    """
    for exc_type, _ in _STATUS_BY_EXCEPTION:
        app.add_exception_handler(exc_type, _handle_mapped_exception)
    app.add_exception_handler(PipelineExecutionError, _handle_pipeline_execution_error)
    app.add_exception_handler(RateLimitExceededError, _handle_rate_limit_exceeded)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
