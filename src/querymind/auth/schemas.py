"""Immutable Pydantic schemas for `querymind.auth` -- request/result shapes, never the ORM
models themselves crossing a service boundary (mirrors every other phase: an engine's public
surface is Pydantic, its persistence is not).

Every model here is `frozen=True, extra="forbid"` -- frozen because nothing downstream should
ever mutate a schema instance in place (a caller that wants a changed value builds a new one),
`extra="forbid"` so a typo'd or unexpected field in an inbound payload (`UserCreate`,
`UserLogin`, `RefreshRequest`) is a validation error, not silently ignored.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from querymind.auth.models import UserRole


class UserCreate(BaseModel):
    """Input to `AuthenticationService.register_user` -- a plaintext password, never persisted
    as such (see `querymind.auth.passwords.hash_password`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class UserLogin(BaseModel):
    """Input to `AuthenticationService.authenticate`. `username` accepts either a username or
    an email -- matching `authenticate`'s own lookup, and the conventional field name FastAPI's
    `OAuth2PasswordRequestForm` uses for the same purpose (Phase 22A Part 2).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    username: str
    password: str


class UserRead(BaseModel):
    """A `User` as returned to a caller -- every field except `password_hash`, which never
    leaves `querymind.auth` in any form.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", from_attributes=True)

    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    role: UserRole
    created_at: datetime
    updated_at: datetime


class TokenPair(BaseModel):
    """The result of a successful login or token refresh."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Input to a future `POST /auth/refresh`/`POST /auth/logout` (Phase 22A Part 2) -- defined
    here now as the schema those endpoints will parse a request body into. `AuthenticationService`
    itself takes a plain `refresh_token: str`, not this wrapper (see the service module's own
    docstring on why it stays HTTP-agnostic); nothing in Part 1 constructs this type yet.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    refresh_token: str


class ApiKeyCreate(BaseModel):
    """Input to `AuthenticationService.create_api_key` / `POST /auth/api-keys`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    expires_at: datetime | None = None


class ApiKeyRead(BaseModel):
    """An `ApiKey` as returned to a caller -- every field except `key_hash`, which never leaves
    `querymind.auth` in any form (mirrors `UserRead` excluding `password_hash`). `key_prefix` is
    the only key-identifying value here; the raw key itself is never in this schema at all --
    see `ApiKeyCreated` for the one response that carries it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", from_attributes=True)

    id: int
    key_prefix: str
    name: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(BaseModel):
    """The result of `POST /auth/api-keys` -- the *only* schema that ever carries a raw API key,
    returned exactly once, at creation. Nothing in `querymind.auth` constructs this a second
    time for the same key; `ApiKeyRead` (metadata only) is what every later read returns.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_key: str
    key: ApiKeyRead


class AuthenticationResult(BaseModel):
    """Bundles a `UserRead` with a `TokenPair` -- provided for a future login endpoint (Phase
    22A Part 2) that wants to return both in one response body. Not produced by any
    `AuthenticationService` method in Part 1, which returns `UserRead` and `TokenPair`
    separately (`authenticate` and `create_token_pair` are deliberately two calls, not one --
    see the service module's own docstring).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    user: UserRead
    tokens: TokenPair
