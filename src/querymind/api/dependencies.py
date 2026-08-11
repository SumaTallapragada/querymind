"""Shared FastAPI dependencies.

Every dependency callable here does exactly one thing: read something
already constructed (`Settings`, the `ApplicationContainer`, one engine
off it) and hand it to a route via `Depends(...)`. No dependency
constructs an engine itself -- `ApplicationContainer.build` (called once,
in `querymind.api.lifespan`) already did that; this module only resolves
references to what already exists.

`get_db_session`/`DbSessionDep` are unchanged from Phase 1 (moved here
from the now-removed `api/deps.py`, not rewritten) and back the existing
`/api/v1/health/ready` endpoint, which predates this phase and is left
exactly as it was.

`get_container` takes an `HTTPConnection`, not a `Request` -- Starlette's
common base class for both `Request` (HTTP) and `WebSocket` -- because
`querymind.streaming.websocket`'s `/ws/query` (Phase 17) resolves
`QueryMindEngineDep`/`EventBusDep`/`LoggerDep` too, and FastAPI only
auto-injects a concrete `Request` for HTTP routes / a concrete
`WebSocket` for WebSocket routes, never either for the other. Every
dependency built on top of `ContainerDep` therefore already works for
both transports with no changes of its own.

`SettingsDep` reads `container.settings`, *not*
`querymind.core.config.get_settings()` (the `lru_cache`d process-wide
singleton `create_app` falls back to when no explicit `Settings` is
given) -- the two can genuinely differ: a test builds its own `Settings`
instance and passes it to `create_app(settings=...)` explicitly, but the
very first call to `get_settings()` anywhere in the process (by any
test, in any order) permanently caches *that* call's result for the rest
of the process. A route depending on `get_settings` directly would
silently see whichever `Settings` happened to be constructed first,
never necessarily the one its own app was actually built from -- found
via `GET /settings` (Phase 18) returning the real `.env`'s database name
instead of a test's hermetic one.

`CurrentUser`/`OptionalUser`/`RequireAdminUser` (Phase 22A Part 2) resolve a bearer token
against `AuthenticationService.get_current_user` -- the one call site for "what does this
token mean," matching this whole module's own rule that nothing here re-derives what an
already-built collaborator already knows how to do. Neither of them catches
`querymind.auth.exceptions.AuthenticationError` itself: it propagates to the same
mapped-exception machinery every other engine's exceptions already go through
(`querymind.api.exception_handlers`), so a bad/expired/revoked token becomes a `401` (or a
deactivated account a `403`) with no special-casing here -- the only thing genuinely unique
to *this* dependency is that "no token at all" isn't an exception from anything, so that one
case is still raised directly, as an `HTTPException`.

`CurrentUser` (Phase 22D) additionally resolves an `X-API-Key` header via
`AuthenticationService.authenticate_api_key`, converging onto the same `UserRead` a JWT would --
every `Require*` dependency below is therefore already API-key-aware with no changes of its own.
`CurrentUserJwtOnly` is the one deliberate exception: the `/auth/api-keys*` management routes use
it instead of `CurrentUser` specifically so an API key can never be used to manage API keys.

`RequireAdmin`/`RequireAnalyst`/`RequireViewer`/`RequireAnyRole` (Phase 22B) are the
authorization counterpart: every one of them takes `CurrentUser` (never re-extracts or
re-decodes a token of its own) and calls one of `AuthenticationService.require_role`/
`require_any_role` -- no role comparison happens in this module either, only in the service,
matching this whole module's "resolve, don't re-derive" rule one layer further. Like
`get_current_user`, none of them catches the `querymind.auth.exceptions.AuthorizationError`
either raises; it propagates to `querymind.api.exception_handlers` the same way.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from querymind.api.client_info import get_attempted_username, get_client_ip, get_user_agent
from querymind.api.container import ApplicationContainer
from querymind.auth.exceptions import AuthenticationError
from querymind.auth.models import UserRole
from querymind.auth.schemas import UserRead
from querymind.auth.service import AuthenticationService
from querymind.core.config import Settings
from querymind.db.session import transactional_session
from querymind.observability.diagnostics import DiagnosticsEngine
from querymind.observability.health import HealthCheckEngine
from querymind.observability.logger import Logger
from querymind.observability.metrics import MetricsCollector
from querymind.orchestrator import QueryMindEngine
from querymind.result_formatter import ResultFormatterEngine
from querymind.security.audit import AuditEventType, AuditLogger
from querymind.security.exceptions import RateLimitExceededError
from querymind.security.rate_limiter import RateLimitDecision, RateLimiter
from querymind.sql_execution import SQLExecutionEngine
from querymind.sql_validation import SQLValidationEngine
from querymind.streaming.event_bus import EventBus


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a transaction-scoped async DB session for the current request.

    The session factory is read off ``app.state`` (populated once at
    startup in ``querymind.api.lifespan``) rather than constructed here,
    so the engine's connection pool is created exactly once per process
    and shared across all requests.
    """
    session_factory = request.app.state.session_factory
    async with transactional_session(session_factory) as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_container(conn: HTTPConnection) -> ApplicationContainer:
    """Return the one `ApplicationContainer` built at startup, off `app.state`."""
    container: ApplicationContainer = conn.app.state.container
    return container


ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


def get_settings(container: ContainerDep) -> Settings:
    return container.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_query_mind_engine(container: ContainerDep) -> QueryMindEngine:
    return container.query_mind_engine


def get_sql_validation_engine(container: ContainerDep) -> SQLValidationEngine:
    return container.sql_validation_engine


def get_sql_execution_engine(container: ContainerDep) -> SQLExecutionEngine:
    return container.sql_execution_engine


def get_result_formatter_engine(container: ContainerDep) -> ResultFormatterEngine:
    return container.result_formatter_engine


def get_health_check_engine(container: ContainerDep) -> HealthCheckEngine:
    return container.health_check_engine


def get_diagnostics_engine(container: ContainerDep) -> DiagnosticsEngine:
    return container.diagnostics_engine


def get_metrics_collector(container: ContainerDep) -> MetricsCollector:
    return container.metrics_collector


def get_logger(container: ContainerDep) -> Logger:
    return container.logger


def get_event_bus(container: ContainerDep) -> EventBus:
    return container.event_bus


QueryMindEngineDep = Annotated[QueryMindEngine, Depends(get_query_mind_engine)]
SQLValidationEngineDep = Annotated[SQLValidationEngine, Depends(get_sql_validation_engine)]
SQLExecutionEngineDep = Annotated[SQLExecutionEngine, Depends(get_sql_execution_engine)]
ResultFormatterEngineDep = Annotated[ResultFormatterEngine, Depends(get_result_formatter_engine)]
HealthCheckEngineDep = Annotated[HealthCheckEngine, Depends(get_health_check_engine)]
DiagnosticsEngineDep = Annotated[DiagnosticsEngine, Depends(get_diagnostics_engine)]
MetricsCollectorDep = Annotated[MetricsCollector, Depends(get_metrics_collector)]
LoggerDep = Annotated[Logger, Depends(get_logger)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]


def get_authentication_service(container: ContainerDep) -> AuthenticationService:
    return container.authentication_service


AuthenticationServiceDep = Annotated[AuthenticationService, Depends(get_authentication_service)]


def get_audit_logger(container: ContainerDep) -> AuditLogger:
    return container.audit_logger


AuditLoggerDep = Annotated[AuditLogger, Depends(get_audit_logger)]


def get_rate_limiter(container: ContainerDep) -> RateLimiter:
    return container.rate_limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


# `auto_error=False`: a missing/malformed `Authorization` header becomes `None`, not an
# automatic 401 -- `OptionalUser` needs that to mean "anonymous," and `CurrentUser`/
# `get_current_user` below raises its own, explicit 401 for the same case, with the same
# `WWW-Authenticate` header a `True` scheme would have added automatically. `tokenUrl` is
# OpenAPI metadata only (what Swagger's docs point at as "get a token here") -- `POST
# /auth/login` (`querymind.api.routers.auth`) accepts a JSON body, not the OAuth2 password
# flow's form-encoded one, matching every other endpoint in this API; using
# `OAuth2PasswordBearer` is about standardized *bearer-token extraction*, not adopting the
# full OAuth2 password-grant request shape for login itself.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)

# `auto_error=False` for the same reason as `_oauth2_scheme` above: a missing `X-API-Key`
# header should mean "this caller is using a JWT instead," not an automatic 401 -- `get_current_
# user` below decides what a *missing* credential means; this extractor only ever answers "was
# this header present."
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_optional_current_user(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    auth_service: AuthenticationServiceDep,
) -> UserRead | None:
    """`None` if no bearer token was given at all (an anonymous request); otherwise delegates
    to `get_current_user`'s same rules -- a token that *was* given but is bad/expired/revoked
    still raises (mapped to `401`/`403` the same way), rather than silently degrading to
    anonymous, since that's far more likely a caller bug worth surfacing than a legitimate
    "not logged in."
    """
    if token is None:
        return None
    return await auth_service.get_current_user(token)


OptionalUser = Annotated[UserRead | None, Depends(get_optional_current_user)]


async def _resolve_jwt_user(token: str | None, auth_service: AuthenticationService) -> UserRead:
    """Bearer-JWT-only resolution -- the exact pre-Phase-22D `get_current_user` body, kept as
    its own function so both `get_current_user` (dual credential) and `get_current_user_jwt_only`
    (JWT-only, see below) share it rather than duplicating the "no token at all" check.

    Raises `401` directly, here, only for "no token at all" -- every other failure
    (bad/expired/wrong-type token, an account since deactivated) is
    `AuthenticationService.get_current_user` raising a `querymind.auth.exceptions.AuthenticationError`
    subclass, mapped to its HTTP status the same way every other engine's exceptions already
    are (`querymind.api.exception_handlers`); this function does not catch it.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await auth_service.get_current_user(token)


async def get_current_user_jwt_only(
    request: Request,
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    auth_service: AuthenticationServiceDep,
) -> UserRead:
    """Bearer-JWT identity only -- never consults `X-API-Key` (Phase 22D). The one dependency
    the `/auth/api-keys*` management routes use, so an API key can never be used to create,
    list, or revoke API keys: that guarantee is structural (this function has no code path that
    even looks at the header), not a convention a future route could accidentally violate.
    """
    user = await _resolve_jwt_user(token, auth_service)
    request.state.user = user
    return user


CurrentUserJwtOnly = Annotated[UserRead, Depends(get_current_user_jwt_only)]


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    api_key: Annotated[str | None, Depends(_api_key_header)],
    auth_service: AuthenticationServiceDep,
    audit_logger: AuditLoggerDep,
) -> UserRead:
    """The authenticated user, resolved from either an `Authorization: Bearer <token>` header
    (the original, unchanged JWT path) or an `X-API-Key` header (Phase 22D) -- both resolve to
    the same `UserRead`, so every `Require*` dependency built on top of `CurrentUser` below
    (`RequireAdmin`/`RequireAnalyst`/`RequireViewer`/`RequireAnyRole`) needs no change at all to
    accept either credential; none of them re-derives identity themselves, they only ever take
    `CurrentUser` and check `.role`.

    An API key takes precedence when both happen to be present (an unlikely caller mistake, not
    a security decision -- there is no scenario where sending both is meaningful). Also stashes
    the resolved user on `request.state.user`, giving `querymind.api.exception_handlers` a
    reliable, already-established place to read "who is this" for audit-logging an authorization
    denial (Phase 22D) without re-decoding a token/key a second time.

    Every API-key-authenticated request is audited here (success or failure) -- this is the one
    place both outcomes are known precisely, for *any* route a key might hit, not just the
    `/auth/*` ones a route body could instrument itself. The JWT path is deliberately not
    audited per-request the same way: login/refresh/logout already mark every JWT session
    boundary (`querymind.api.routers.auth`), and auditing every single JWT-authenticated request
    on top of that would be pure volume with no new security signal.
    """
    if api_key is not None:
        try:
            user = await auth_service.authenticate_api_key(api_key)
        except AuthenticationError as exc:
            await audit_logger.record(
                AuditEventType.API_KEY_AUTH_FAILURE,
                success=False,
                ip_address=get_client_ip(request, trust_proxy_headers=_trust_proxy(request)),
                user_agent=get_user_agent(request),
                request_id=getattr(request.state, "request_id", None),
                correlation_id=getattr(request.state, "correlation_id", None),
                resource=request.url.path,
                metadata={"error_type": type(exc).__name__},
            )
            raise
        await audit_logger.record(
            AuditEventType.API_KEY_AUTH_SUCCESS,
            success=True,
            actor_user_id=user.id,
            actor_username=user.username,
            ip_address=get_client_ip(request, trust_proxy_headers=_trust_proxy(request)),
            user_agent=get_user_agent(request),
            request_id=getattr(request.state, "request_id", None),
            correlation_id=getattr(request.state, "correlation_id", None),
            resource=request.url.path,
        )
    else:
        user = await _resolve_jwt_user(token, auth_service)
    request.state.user = user
    return user


def _trust_proxy(request: Request) -> bool:
    settings: Settings = request.app.state.settings
    return settings.trust_proxy_headers


CurrentUser = Annotated[UserRead, Depends(get_current_user)]

#: Same dependency as `CurrentUser`, under the name a route reaches for when the point is
#: "this requires authentication" rather than "give me whoever's logged in" -- both resolve
#: identically today; kept as its own name so Phase 22B (authorization) has a natural, already-
#: adopted place to add a required-role parameter without every existing route's annotation
#: needing to change.
RequireAuthenticatedUser = CurrentUser


async def get_admin_user(user: CurrentUser) -> UserRead:
    """`CurrentUser`, plus asserting `is_superuser` -- the closest thing to a "role" that
    already exists on `User` (Phase 22A Part 1); not a roles/permissions system (out of scope
    through Phase 22A), just a direct check of a field that was already there.
    """
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires administrator privileges.",
        )
    return user


RequireAdminUser = Annotated[UserRead, Depends(get_admin_user)]


# -- Authorization (Phase 22B) -----------------------------------------------------------------
#
# Three fixed-role dependencies (`RequireAdmin`/`RequireAnalyst`/`RequireViewer`, ranked --
# `AuthenticationService.require_role`'s own docstring explains what "ranked" means: `ADMIN`
# satisfies a `RequireAnalyst`/`RequireViewer` route too) plus one general combinator
# (`RequireAnyRole`) for a set of roles the rank order alone can't express. Every one of these
# is genuinely reusable infrastructure, the same way `OptionalUser`/`RequireAdminUser` above
# were added in Phase 22A Part 2 without every route using them immediately.


async def get_admin_required_user(
    user: CurrentUser, auth_service: AuthenticationServiceDep
) -> UserRead:
    auth_service.require_role(user, UserRole.ADMIN)
    return user


async def get_analyst_required_user(
    user: CurrentUser, auth_service: AuthenticationServiceDep
) -> UserRead:
    """Ranked: an `ADMIN` satisfies this too (rank 3 >= rank 2) -- this is what "Query:
    ANALYST or ADMIN"/"Streaming: ANALYST or ADMIN" (the route-protection matrix) resolve to;
    no separate `RequireAnyRole(ANALYST, ADMIN)` is needed for either.
    """
    auth_service.require_role(user, UserRole.ANALYST)
    return user


async def get_viewer_required_user(
    user: CurrentUser, auth_service: AuthenticationServiceDep
) -> UserRead:
    """Ranked at the floor -- `VIEWER`, `ANALYST`, and `ADMIN` all satisfy this; in practice
    equivalent to `CurrentUser` for any user with a role at all (every role outranks or equals
    `VIEWER`), but spelled out for a route that wants to document "any role, explicitly" rather
    than "merely authenticated."
    """
    auth_service.require_role(user, UserRole.VIEWER)
    return user


RequireAdmin = Annotated[UserRead, Depends(get_admin_required_user)]
RequireAnalyst = Annotated[UserRead, Depends(get_analyst_required_user)]
RequireViewer = Annotated[UserRead, Depends(get_viewer_required_user)]


def RequireAnyRole(*roles: UserRole) -> Any:  # noqa: N802 -- named like the dependency (`RequireX`)
    # it stands in for, per this module's own established `Require*` convention; called as
    # `RequireAnyRole(UserRole.ADMIN, UserRole.VIEWER)` *inside* `Annotated[...]`, not awaited
    # or instantiated directly. Returns `Any`, not `Depends`/`UserRead`: `fastapi.Depends`'
    # own stub return type is `Any` (by design -- so it type-checks as whatever the `Annotated`
    # wrapping it declares), and that is the accurate type of what's actually returned here.
    """A `Depends()` factory for an explicit, non-hierarchical set of acceptable roles --
    `Annotated[UserRead, RequireAnyRole(UserRole.ADMIN, UserRole.VIEWER)]`. Prefer
    `RequireAdmin`/`RequireAnalyst`/`RequireViewer` when a plain rank threshold already says
    what you mean; reach for this only when it doesn't (e.g. "ADMIN or VIEWER, but not
    ANALYST").
    """

    async def _check(user: CurrentUser, auth_service: AuthenticationServiceDep) -> UserRead:
        auth_service.require_any_role(user, *roles)
        return user

    return Depends(_check)


# -- Rate limiting (Phase 22D) -------------------------------------------------------------
#
# Every dependency below does the same three things: build a bucket key from a scope name and
# an identity, call `RateLimiterDep.check(...)` with the matching `Settings` limit, and raise
# `RateLimitExceededError` if it's exhausted -- never a bespoke `JSONResponse` built inline (the
# same "one central place maps an exception to a response" rule every other engine's exceptions
# already follow, via `querymind.api.exception_handlers`). None of this touches `RequireAdmin`/
# `RequireAnalyst`/`RequireViewer`/`RequireAnyRole` above at all -- rate limiting and RBAC are
# independent, stackable dependencies, not a change to either.
#
# `check_query_rate_limit` takes `CurrentUser`, not `RequireAnalyst` -- FastAPI resolves a given
# dependency callable at most once per request (`use_cache=True` by default), so a route that
# also depends on `RequireAnalyst` (which itself depends on `CurrentUser`) does not re-run
# `get_current_user` a second time, re-authenticate, or double-audit an API-key request; both
# dependencies simply share the one already-resolved `UserRead`. This is also how an API-key-
# authenticated caller reaches this limit at all: `CurrentUser` resolves a key to the same
# `UserRead` a JWT would (see its own docstring), so `f"query:user:{user.id}"` is keyed on the
# *owning* user either way -- no second identity system, exactly as the approved design requires.


def _raise_if_blocked(decision: RateLimitDecision) -> None:
    """Shared by every dependency below -- the one place a blocked `RateLimitDecision` becomes
    `RateLimitExceededError`, so the message text and `retry_after_seconds` propagation only
    exist once.
    """
    if not decision.allowed:
        raise RateLimitExceededError(
            "Too many requests. Please slow down and try again shortly.",
            retry_after_seconds=decision.retry_after_seconds,
        )


async def check_general_rate_limit(
    request: Request, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    """The one coarse, application-wide ceiling -- attached once, to the whole `api_router`
    (`querymind.api.app`), not to any individual route. Every route under `/api/v1` is subject
    to this even when a tighter, more specific limit also applies on top of it.
    """
    capacity = settings.rate_limit_general_per_minute
    ip = get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
    decision = await limiter.check(
        f"general:ip:{ip}", capacity=capacity, refill_per_second=capacity / 60
    )
    _raise_if_blocked(decision)


GeneralRateLimit = Annotated[None, Depends(check_general_rate_limit)]


async def check_login_rate_limit(
    request: Request, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    """Two independent buckets, both must have capacity: one per calling IP, one per *attempted*
    username (read straight from the request body -- `UserLogin.username` accepts either a
    username or an email; there is no separate `email` field to prefer, see that schema's own
    docstring) -- so distributed credential stuffing against one account from many IPs is
    throttled by the second bucket even though the first never fills up.
    """
    capacity = settings.rate_limit_login_per_minute
    refill_per_second = capacity / 60
    ip = get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
    ip_decision = await limiter.check(
        f"login:ip:{ip}", capacity=capacity, refill_per_second=refill_per_second
    )
    username = await get_attempted_username(request)
    username_decision = None
    if username:
        username_decision = await limiter.check(
            f"login:username:{username}", capacity=capacity, refill_per_second=refill_per_second
        )
    blocked = next(
        (d for d in (ip_decision, username_decision) if d is not None and not d.allowed), None
    )
    if blocked is not None:
        _raise_if_blocked(blocked)


LoginRateLimit = Annotated[None, Depends(check_login_rate_limit)]


async def check_register_rate_limit(
    request: Request, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    capacity = settings.rate_limit_register_per_hour
    ip = get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
    decision = await limiter.check(
        f"register:ip:{ip}", capacity=capacity, refill_per_second=capacity / 3600
    )
    _raise_if_blocked(decision)


RegisterRateLimit = Annotated[None, Depends(check_register_rate_limit)]


async def check_refresh_rate_limit(
    request: Request, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    capacity = settings.rate_limit_refresh_per_minute
    ip = get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
    decision = await limiter.check(
        f"refresh:ip:{ip}", capacity=capacity, refill_per_second=capacity / 60
    )
    _raise_if_blocked(decision)


RefreshRateLimit = Annotated[None, Depends(check_refresh_rate_limit)]


async def check_query_rate_limit(
    user: CurrentUser, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    """Keyed on the authenticated user id -- shared by every `/query*` route and `/query/stream`
    (`RateLimitQuery`) and, checked directly rather than via `Depends()`, by `/ws/query`
    (`querymind.streaming.websocket`, which cannot use FastAPI dependencies on a WebSocket route
    at all -- see that module's own docstring) so every surface that runs the same expensive
    pipeline shares the exact same per-user bucket.
    """
    capacity = settings.rate_limit_query_per_minute
    decision = await limiter.check(
        f"query:user:{user.id}", capacity=capacity, refill_per_second=capacity / 60
    )
    _raise_if_blocked(decision)


RateLimitQuery = Annotated[None, Depends(check_query_rate_limit)]
