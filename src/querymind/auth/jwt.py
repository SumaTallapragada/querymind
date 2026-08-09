"""JWT issuance and verification -- access and refresh tokens, `PyJWT` underneath.

Deliberately takes every configuration value (`secret_key`, `algorithm`, expiry) as an explicit
parameter on every function, rather than reaching into `querymind.core.config.Settings` --
Phase 22A Part 1 builds `querymind.auth` as a self-contained library with no framework or
application-config coupling; wiring these from `Settings` is the API layer's job (Part 2).

Claims on every token: `sub` (the user id, as a string -- JWT's registered `sub` claim is
conventionally a string even for a numeric identity), `jti` (a fresh UUID4 per token, unique
even for two tokens issued in the same second), `iat`/`exp` (issued-at/expiry, both UTC), and
`type` (`"access"` or `"refresh"`) -- the one non-registered claim this module adds, so a token
of one type can never be silently accepted where the other is required.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt as pyjwt

from querymind.auth.exceptions import InvalidTokenError, TokenExpiredError

TokenType = Literal["access", "refresh"]

DEFAULT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS = 14


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """The decoded, validated claims of one JWT -- what `decode_token`/`validate_token` return."""

    sub: str
    jti: str
    iat: datetime
    exp: datetime
    type: TokenType


def _encode(
    *,
    subject: str,
    token_type: TokenType,
    secret_key: str,
    algorithm: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
    }
    return pyjwt.encode(payload, secret_key, algorithm=algorithm)


def create_access_token(
    subject: str,
    *,
    secret_key: str,
    algorithm: str = DEFAULT_ALGORITHM,
    expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
) -> str:
    """Issue a short-lived access token for `subject` (the user id, as a string).

    Never persisted anywhere -- an access token is validated purely by its signature and `exp`;
    revoking one before it naturally expires is out of scope for Phase 22A (see
    `querymind.auth.cache`'s own docstring for why).
    """
    return _encode(
        subject=subject,
        token_type="access",
        secret_key=secret_key,
        algorithm=algorithm,
        expires_delta=timedelta(minutes=expire_minutes),
    )


def create_refresh_token(
    subject: str,
    *,
    secret_key: str,
    algorithm: str = DEFAULT_ALGORITHM,
    expire_days: int = DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS,
) -> tuple[str, TokenClaims]:
    """Issue a long-lived refresh token for `subject`, returning both the encoded token string
    and its own decoded claims -- unlike `create_access_token`, a refresh token's `jti`/`exp`
    must be persisted (`AuthenticationRepository.store_refresh_token`) so it can later be looked
    up and revoked; returning the claims alongside the token avoids the caller immediately
    decoding what it just encoded.
    """
    token = _encode(
        subject=subject,
        token_type="refresh",
        secret_key=secret_key,
        algorithm=algorithm,
        expires_delta=timedelta(days=expire_days),
    )
    return token, decode_token(token, secret_key=secret_key, algorithm=algorithm)


def decode_token(token: str, *, secret_key: str, algorithm: str = DEFAULT_ALGORITHM) -> TokenClaims:
    """Decode and verify `token`'s signature and expiry, returning its claims.

    Raises `TokenExpiredError` if `exp` has passed, `InvalidTokenError` for anything else wrong
    (bad signature, malformed token, a required claim missing) -- never PyJWT's own exception
    types, so callers only ever need to know this package's exception hierarchy.
    """
    try:
        payload = pyjwt.decode(token, secret_key, algorithms=[algorithm])
    except pyjwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("The token has expired.") from exc
    except pyjwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"The token is invalid: {exc}") from exc

    try:
        return TokenClaims(
            sub=payload["sub"],
            jti=payload["jti"],
            iat=datetime.fromtimestamp(payload["iat"], tz=UTC),
            exp=datetime.fromtimestamp(payload["exp"], tz=UTC),
            type=payload["type"],
        )
    except KeyError as exc:
        raise InvalidTokenError(f"The token is missing a required claim: {exc}") from exc


def validate_token(
    token: str, *, secret_key: str, algorithm: str = DEFAULT_ALGORITHM, expected_type: TokenType
) -> TokenClaims:
    """`decode_token`, plus asserting `type == expected_type` -- raises `InvalidTokenError` if
    an access token is presented where a refresh token is required, or vice versa.
    """
    claims = decode_token(token, secret_key=secret_key, algorithm=algorithm)
    if claims.type != expected_type:
        raise InvalidTokenError(f"Expected a {expected_type!r} token, got {claims.type!r}.")
    return claims
