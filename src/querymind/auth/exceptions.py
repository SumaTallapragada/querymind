"""Domain-specific exceptions for `querymind.auth`.

Mirrors every other phase's exception-hierarchy convention (see e.g.
`querymind.sql_execution.exceptions`): one `AuthenticationError` base,
one subclass per distinct failure mode a caller might need to handle
differently. Nothing here is HTTP-aware -- mapping these to a status
code is the API layer's job (Phase 22A Part 2), not this package's.

`AuthorizationError` (Phase 22B) is a deliberately separate hierarchy, not a subclass of
`AuthenticationError` -- the two answer different questions ("who are you" vs. "what are you
allowed to do"), and a caller that wants to handle "not logged in" and "logged in, but not
permitted" differently needs them to never be confusable via `isinstance`.
"""

from __future__ import annotations


class AuthenticationError(Exception):
    """Base class for every exception raised within `querymind.auth`."""


class InvalidCredentialsError(AuthenticationError):
    """Raised by `AuthenticationService.authenticate` on a wrong username/email or password.

    Deliberately the *same* exception for "no such user" and "wrong password" -- a caller
    that distinguished the two would let an attacker enumerate valid usernames/emails.
    """


class InactiveUserError(AuthenticationError):
    """Raised by `AuthenticationService.authenticate` when the credentials are correct but
    `User.is_active` is `False`. Kept distinct from `InvalidCredentialsError`: the password
    *was* right, which is operationally useful to know (e.g. for logging), even though both
    ultimately deny the login.
    """


class DuplicateUserError(AuthenticationError):
    """Raised by `AuthenticationService.register_user` when the username or email is already
    taken -- whether caught by a pre-check query or by the database's own unique constraint
    (a race between two concurrent registrations); see the service's own docstring.
    """


class InvalidTokenError(AuthenticationError):
    """Raised by `jwt.decode_token`/`jwt.validate_token` for any token that fails to decode
    (bad signature, malformed, wrong algorithm) or whose `type` claim doesn't match what the
    caller required (e.g. an access token presented where a refresh token was expected).
    Also raised by `AuthenticationService` when a refresh token's `jti` has no matching
    `RefreshToken` row at all -- a token that was never issued, or whose row no longer exists.
    """


class TokenExpiredError(AuthenticationError):
    """Raised by `jwt.decode_token`/`jwt.validate_token` when a token's `exp` claim is in the
    past, and by `AuthenticationService` when a `RefreshToken` row's own `expires_at` has
    passed (checked independently of the JWT's own `exp`, which is set to the same instant at
    issuance -- this is defense in depth, not a second, different expiry policy).
    """


class RefreshTokenRevokedError(AuthenticationError):
    """Raised by `AuthenticationService` when a refresh token's `jti` resolves to a real,
    unexpired `RefreshToken` row, but `revoked` is `True` -- e.g. reused after `logout()` or
    after being rotated away by an earlier `refresh_tokens()` call.
    """


class InvalidApiKeyError(AuthenticationError):
    """Raised by `AuthenticationService.authenticate_api_key` (Phase 22D) for a key that is
    malformed (no recognizable `qm_` prefix) or whose hash matches no stored `ApiKey` row at
    all -- the API-key analogue of `InvalidCredentialsError`/`InvalidTokenError`.
    """


class ApiKeyExpiredError(AuthenticationError):
    """Raised by `AuthenticationService.authenticate_api_key` when a key's `expires_at` has
    passed -- the API-key analogue of `TokenExpiredError`.
    """


class ApiKeyRevokedError(AuthenticationError):
    """Raised by `AuthenticationService.authenticate_api_key` when a key's `revoked_at` is set --
    the API-key analogue of `RefreshTokenRevokedError`.
    """


class ApiKeyNotFoundError(AuthenticationError):
    """Raised by `AuthenticationService.revoke_api_key` when no key with the given id exists, or
    it belongs to a different user than the (non-admin) caller -- deliberately the same outcome
    for both cases, mirroring `InvalidCredentialsError`'s own "don't let a caller distinguish
    these" rule: a non-owner should not be able to learn whether a given key id exists at all.
    """


class AuthorizationError(Exception):
    """Base class for every exception raised by `querymind.auth`'s role-checking helpers
    (Phase 22B) -- see this module's own docstring for why this is not an `AuthenticationError`
    subclass.
    """


class ForbiddenRoleError(AuthorizationError):
    """Raised by `AuthenticationService.require_role` when a user's role does not meet the
    required rank (`ADMIN` > `ANALYST` > `VIEWER`) -- e.g. a `VIEWER` calling a route that
    requires at least `ANALYST`.
    """


class InsufficientPermissionsError(AuthorizationError):
    """Raised by `AuthenticationService.require_any_role` when a user's role is not among an
    explicit, non-hierarchical set of acceptable roles -- distinct from `ForbiddenRoleError`,
    which is about a single rank threshold, not a specific set.
    """
