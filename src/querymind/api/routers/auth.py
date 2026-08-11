"""`/api/v1/auth/*` -- registration, login, refresh, logout, the current user, and (Phase 22D)
self-service API-key management.

Every route does exactly what `querymind.api.routers.query`'s own docstring describes for
`POST /query`: validate the request body, call the one service method that does the real work,
return its result. No route here catches an exception itself -- every
`querymind.auth.exceptions.AuthenticationError` subclass `AuthenticationService` can raise is
already mapped to an HTTP status by `querymind.api.exception_handlers`, so a route that lets one
propagate gets the correct response automatically, the same way every other phase's routes do;
that same central mapping is also where a *failed* register/login/refresh, or any authorization
denial, gets audit-logged (Phase 22D) -- see that module's own docstring. The one-line audit
calls below are for the *success* half only, which only a route itself can observe.

Every request/response body reuses `querymind.auth.schemas` directly (`UserCreate`, `UserLogin`,
`UserRead`, `TokenPair`, `RefreshRequest`, `ApiKeyCreate`, `ApiKeyRead`, `ApiKeyCreated`) -- no
`api/models/auth.py` duplicate DTOs; see `querymind.api.models.response`'s own docstring for the
established "the engine layer's models *are* the API's models" precedent this follows.

There is no `/auth/change-password` endpoint: `AuthenticationService` (Phase 22A Part 1, frozen
this phase) has no such method, and adding one would be exactly the kind of change to
`src/querymind/auth/` this phase's scope excludes absent a genuine defect -- there isn't one.

The three `/auth/api-keys*` routes (Phase 22D) use `CurrentUserJwtOnly`, not `CurrentUser` --
deliberately: `CurrentUser` now also accepts an `X-API-Key` header, and letting an API key
manage API keys (create one to create another, or list/revoke using one) is exactly the
bootstrapping loophole this phase's approved design closes structurally. Self-service only: a
caller creates/lists/revokes keys for their own account; `revoke` is the one exception, where an
`ADMIN` may revoke any key (`AuthenticationService.revoke_api_key`'s own docstring).

`refresh`/`logout` audit rows carry no `actor_user_id`/`actor_username`: both operate on a bare
refresh token with no username attached, and resolving one would mean either duplicating JWT
decoding here (this router has no access to `AuthenticationService`'s secret/algorithm, by
design) or changing `AuthenticationService.refresh_tokens`/`.logout`'s return shape for an
audit-only need -- both a bigger change than this phase's "no redesign of 22A" scope allows.
IP/user-agent/timing/success are still recorded; a full identity reconciliation is a documented
limitation, not an oversight.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from querymind.api.client_info import get_client_ip, get_user_agent
from querymind.api.dependencies import (
    AuditLoggerDep,
    AuthenticationServiceDep,
    CurrentUser,
    CurrentUserJwtOnly,
    LoginRateLimit,
    RefreshRateLimit,
    RegisterRateLimit,
)
from querymind.auth.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserRead,
)
from querymind.core.config import Settings
from querymind.security.audit import AuditEventType

router = APIRouter(prefix="/auth", tags=["auth"])


async def _audit(
    audit_logger: AuditLoggerDep,
    request: Request,
    event_type: AuditEventType,
    *,
    success: bool,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
) -> None:
    """Shared by every route below -- extracts the same IP/user-agent/request-id/correlation-id
    every call needs, so each route's own audit line stays exactly one call.
    """
    settings: Settings = request.app.state.settings
    await audit_logger.record(
        event_type,
        success=success,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        ip_address=get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers),
        user_agent=get_user_agent(request),
        request_id=getattr(request.state, "request_id", None),
        correlation_id=getattr(request.state, "correlation_id", None),
        resource=request.url.path,
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
    description=(
        "Creates a new user account with a hashed password. Raises 409 if the username or "
        "email is already taken."
    ),
)
async def register(
    request: UserCreate,
    http_request: Request,
    auth_service: AuthenticationServiceDep,
    audit_logger: AuditLoggerDep,
    _rate_limit: RegisterRateLimit,
) -> UserRead:
    user = await auth_service.register_user(
        username=request.username, email=request.email, password=request.password
    )
    await _audit(
        audit_logger,
        http_request,
        AuditEventType.REGISTRATION,
        success=True,
        actor_user_id=user.id,
        actor_username=user.username,
    )
    return user


@router.post(
    "/login",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Log in and obtain an access/refresh token pair",
    description=(
        "Verifies a username (or email) and password and, on success, issues a new access + "
        "refresh token pair. Raises 401 for an unknown username/email or a wrong password "
        "(deliberately indistinguishable -- see `InvalidCredentialsError`), or 403 for a "
        "correct password on a deactivated account."
    ),
)
async def login(
    request: UserLogin,
    http_request: Request,
    auth_service: AuthenticationServiceDep,
    audit_logger: AuditLoggerDep,
    _rate_limit: LoginRateLimit,
) -> TokenPair:
    user = await auth_service.authenticate(request.username, request.password)
    tokens = await auth_service.create_token_pair(user.id)
    await _audit(
        audit_logger,
        http_request,
        AuditEventType.LOGIN_SUCCESS,
        success=True,
        actor_user_id=user.id,
        actor_username=user.username,
    )
    return tokens


@router.post(
    "/refresh",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Exchange a refresh token for a new token pair",
    description=(
        "Rotates `refresh_token` for a new access + refresh pair; the given refresh token is "
        "revoked as part of this call and can never be reused, whether or not the new pair is "
        "ever used. Raises 401 for a missing, expired, or already-revoked refresh token."
    ),
)
async def refresh(
    request: RefreshRequest,
    http_request: Request,
    auth_service: AuthenticationServiceDep,
    audit_logger: AuditLoggerDep,
    _rate_limit: RefreshRateLimit,
) -> TokenPair:
    tokens = await auth_service.refresh_tokens(request.refresh_token)
    await _audit(audit_logger, http_request, AuditEventType.REFRESH_SUCCESS, success=True)
    return tokens


@router.post(
    "/logout",
    response_model=None,  # explicit: a bare `-> None` return annotation alone still makes
    # FastAPI infer an (empty) response model, which trips its own "204 must have no body"
    # assertion at route-registration time -- `response_model=None` is the documented fix.
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token",
    description=(
        "Revokes `refresh_token`. Does not invalidate any access token already issued from it "
        "-- an access token is validated purely by signature and expiry, so it simply expires "
        "on its own; see `AuthenticationService.logout`."
    ),
)
async def logout(
    request: RefreshRequest,
    http_request: Request,
    auth_service: AuthenticationServiceDep,
    audit_logger: AuditLoggerDep,
) -> None:
    await auth_service.logout(request.refresh_token)
    await _audit(audit_logger, http_request, AuditEventType.LOGOUT, success=True)


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="The currently authenticated user",
    description=(
        "Resolves the caller's identity from an `Authorization: Bearer <access_token>` header "
        "or an `X-API-Key` header (Phase 22D)."
    ),
)
async def me(user: CurrentUser) -> UserRead:
    return user


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key for the caller's own account",
    description=(
        "Issues a new API key that authenticates as the caller and inherits their role "
        "exactly. The raw key is returned in this response only -- it cannot be retrieved "
        "again later. Requires a JWT (`Authorization: Bearer`); an API key cannot be used to "
        "create another API key."
    ),
)
async def create_api_key(
    request: ApiKeyCreate,
    http_request: Request,
    user: CurrentUserJwtOnly,
    auth_service: AuthenticationServiceDep,
    audit_logger: AuditLoggerDep,
) -> ApiKeyCreated:
    created = await auth_service.create_api_key(
        user_id=user.id, name=request.name, expires_at=request.expires_at
    )
    await _audit(
        audit_logger,
        http_request,
        AuditEventType.API_KEY_CREATED,
        success=True,
        actor_user_id=user.id,
        actor_username=user.username,
    )
    return created


@router.get(
    "/api-keys",
    response_model=list[ApiKeyRead],
    status_code=status.HTTP_200_OK,
    summary="List the caller's own API keys",
    description=(
        "Metadata only (prefix, name, timestamps) -- never a key hash or raw key. Requires a "
        "JWT; an API key cannot be used to list API keys."
    ),
)
async def list_api_keys(
    user: CurrentUserJwtOnly, auth_service: AuthenticationServiceDep
) -> list[ApiKeyRead]:
    return await auth_service.list_api_keys(user.id)


@router.delete(
    "/api-keys/{key_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    description=(
        "Revokes the given key -- the caller's own, or any key if the caller is `ADMIN`. "
        "Raises 404 both when the key doesn't exist and when it belongs to a different, "
        "non-admin caller (deliberately indistinguishable). Requires a JWT; an API key cannot "
        "be used to revoke API keys."
    ),
)
async def revoke_api_key(
    key_id: int,
    http_request: Request,
    user: CurrentUserJwtOnly,
    auth_service: AuthenticationServiceDep,
    audit_logger: AuditLoggerDep,
) -> None:
    await auth_service.revoke_api_key(requesting_user=user, key_id=key_id)
    await _audit(
        audit_logger,
        http_request,
        AuditEventType.API_KEY_REVOKED,
        success=True,
        actor_user_id=user.id,
        actor_username=user.username,
    )
