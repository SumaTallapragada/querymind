"""Authentication and authorization -- Phase 22A Part 1 (authentication core) and Phase 22B
(role-based authorization), both independent of FastAPI/HTTP. User accounts, Argon2/bcrypt
password hashing, JWT access/refresh tokens with a persisted, revocable refresh-token lifecycle,
and three ranked roles (`ADMIN` > `ANALYST` > `VIEWER`).

The public surface is `AuthenticationService`: authentication (`register_user`, `authenticate`,
`create_token_pair`, `refresh_tokens`, `logout`, `validate_refresh_token`, `get_current_user`)
and authorization (`has_role`, `is_admin`, `require_role`, `require_any_role`), backed by
`AuthenticationRepository`. Wiring this into the FastAPI service layer (routes, dependencies,
`ApplicationContainer`) is Phase 22A Part 2 / Phase 22B -- nothing here imports `fastapi`.
"""

from __future__ import annotations

from querymind.auth.cache import AuthenticationCache, NoOpAuthenticationCache
from querymind.auth.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DuplicateUserError,
    ForbiddenRoleError,
    InactiveUserError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)
from querymind.auth.jwt import (
    TokenClaims,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_token,
)
from querymind.auth.models import AuthBase, RefreshToken, User, UserRole
from querymind.auth.passwords import hash_password, verify_password
from querymind.auth.repository import AuthenticationRepository
from querymind.auth.schemas import (
    AuthenticationResult,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserRead,
)
from querymind.auth.serializer import AuthenticationSerializer
from querymind.auth.service import AuthenticationService

__all__ = [
    "AuthBase",
    "AuthenticationCache",
    "AuthenticationError",
    "AuthenticationRepository",
    "AuthenticationResult",
    "AuthenticationSerializer",
    "AuthenticationService",
    "AuthorizationError",
    "DuplicateUserError",
    "ForbiddenRoleError",
    "InactiveUserError",
    "InsufficientPermissionsError",
    "InvalidCredentialsError",
    "InvalidTokenError",
    "NoOpAuthenticationCache",
    "RefreshRequest",
    "RefreshToken",
    "RefreshTokenRevokedError",
    "TokenClaims",
    "TokenExpiredError",
    "TokenPair",
    "User",
    "UserCreate",
    "UserLogin",
    "UserRead",
    "UserRole",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "validate_token",
    "verify_password",
]
