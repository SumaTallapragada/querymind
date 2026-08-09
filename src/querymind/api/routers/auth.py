"""`/api/v1/auth/*` -- registration, login, refresh, logout, and the current user.

Every route does exactly what `querymind.api.routers.query`'s own docstring describes for
`POST /query`: validate the request body, call the one service method that does the real work,
return its result. No route here catches an exception itself -- every
`querymind.auth.exceptions.AuthenticationError` subclass `AuthenticationService` can raise is
already mapped to an HTTP status by `querymind.api.exception_handlers`, so a route that lets one
propagate gets the correct response automatically, the same way every other phase's routes do.

Every request/response body reuses `querymind.auth.schemas` directly (`UserCreate`, `UserLogin`,
`UserRead`, `TokenPair`, `RefreshRequest`) -- no `api/models/auth.py` duplicate DTOs; see
`querymind.api.models.response`'s own docstring for the established "the engine layer's models
*are* the API's models" precedent this follows.

There is no `/auth/change-password` endpoint: `AuthenticationService` (Phase 22A Part 1, frozen
this phase) has no such method, and adding one would be exactly the kind of change to
`src/querymind/auth/` this phase's scope excludes absent a genuine defect -- there isn't one.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from querymind.api.dependencies import AuthenticationServiceDep, CurrentUser
from querymind.auth.schemas import RefreshRequest, TokenPair, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


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
async def register(request: UserCreate, auth_service: AuthenticationServiceDep) -> UserRead:
    return await auth_service.register_user(
        username=request.username, email=request.email, password=request.password
    )


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
async def login(request: UserLogin, auth_service: AuthenticationServiceDep) -> TokenPair:
    user = await auth_service.authenticate(request.username, request.password)
    return await auth_service.create_token_pair(user.id)


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
async def refresh(request: RefreshRequest, auth_service: AuthenticationServiceDep) -> TokenPair:
    return await auth_service.refresh_tokens(request.refresh_token)


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
async def logout(request: RefreshRequest, auth_service: AuthenticationServiceDep) -> None:
    await auth_service.logout(request.refresh_token)


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="The currently authenticated user",
    description="Resolves the caller's identity from the `Authorization: Bearer <access_token>` header.",
)
async def me(user: CurrentUser) -> UserRead:
    return user
