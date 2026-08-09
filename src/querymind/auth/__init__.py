"""Authentication -- Phase 22A Part 1: a self-contained authentication library, independent of
FastAPI/HTTP. User accounts, Argon2/bcrypt password hashing, and JWT access/refresh tokens with
a persisted, revocable refresh-token lifecycle.

The public surface is `AuthenticationService` (`register_user`, `authenticate`,
`create_token_pair`, `refresh_tokens`, `logout`, `validate_refresh_token`) backed by
`AuthenticationRepository`. Wiring this into the FastAPI service layer (routes, dependencies,
`ApplicationContainer`) is Phase 22A Part 2 -- nothing here imports `fastapi`.
"""

from __future__ import annotations

from querymind.auth.cache import AuthenticationCache, NoOpAuthenticationCache
from querymind.auth.exceptions import (
    AuthenticationError,
    DuplicateUserError,
    InactiveUserError,
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
from querymind.auth.models import AuthBase, RefreshToken, User
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
    "DuplicateUserError",
    "InactiveUserError",
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
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "validate_token",
    "verify_password",
]
