"""`AuthenticationService` -- the one place every authentication business rule lives.

No FastAPI import, no HTTP concept (a status code, a header, a cookie) anywhere in this module
-- Phase 22A Part 1 builds `querymind.auth` as a self-contained library, usable from a route, a
CLI script, or a test with no web framework involved at all. Wiring this service into FastAPI
(routes, an `OAuth2PasswordBearer` dependency, exception-to-status-code mapping) is Phase 22A
Part 2's job.

`AuthenticationRepository` enforces nothing (see its own docstring); every decision --
"is this username taken," "is this the right password," "is this refresh token still good" --
is made exactly once, here, and nowhere else in `querymind.auth`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from querymind.auth import jwt as jwt_module
from querymind.auth.exceptions import (
    DuplicateUserError,
    ForbiddenRoleError,
    InactiveUserError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)
from querymind.auth.jwt import DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES, DEFAULT_ALGORITHM
from querymind.auth.jwt import DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS as _DEFAULT_REFRESH_DAYS
from querymind.auth.models import RefreshToken, UserRole
from querymind.auth.passwords import hash_password, verify_password
from querymind.auth.repository import AuthenticationRepository
from querymind.auth.schemas import TokenPair, UserRead

#: `ADMIN` > `ANALYST` > `VIEWER` -- what "ranked" means for `require_role`. A plain module-level
#: dict, not a method on `UserRole` itself: ranking is an *authorization* concept (Phase 22B),
#: while `querymind.auth.models` stays persistence-only (column/enum definitions, no business
#: logic) -- the same separation `querymind.auth.repository`'s own docstring already draws
#: between "the shape of the data" and "the rules about it."
_ROLE_RANK: dict[UserRole, int] = {
    UserRole.VIEWER: 1,
    UserRole.ANALYST: 2,
    UserRole.ADMIN: 3,
}


class AuthenticationService:
    """Registration, login, and refresh-token lifecycle. Constructor-injected throughout --
    holds a repository and the JWT configuration it needs, nothing global, nothing cached.
    """

    def __init__(
        self,
        repository: AuthenticationRepository,
        *,
        jwt_secret_key: str,
        jwt_algorithm: str = DEFAULT_ALGORITHM,
        access_token_expire_minutes: int = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
        refresh_token_expire_days: int = _DEFAULT_REFRESH_DAYS,
    ) -> None:
        self._repository = repository
        self._jwt_secret_key = jwt_secret_key
        self._jwt_algorithm = jwt_algorithm
        self._access_token_expire_minutes = access_token_expire_minutes
        self._refresh_token_expire_days = refresh_token_expire_days

    async def register_user(self, *, username: str, email: str, password: str) -> UserRead:
        """Create a new account. Raises `DuplicateUserError` if `username`/`email` is taken.

        Checked twice, deliberately: a pre-check query gives a clean, immediate error for the
        overwhelmingly common case (someone just registering with a name that's already in
        use), while the `IntegrityError` catch around the actual insert is what makes this
        correct even under a genuine race (two concurrent registrations for the same username) --
        the pre-check alone cannot close that window, only the database's own unique constraint can.
        """
        existing = await self._repository.get_by_username(
            username
        ) or await self._repository.get_by_email(email)
        if existing is not None:
            raise DuplicateUserError(f"Username {username!r} or email {email!r} is already taken.")

        password_hash = hash_password(password)
        try:
            user = await self._repository.create_user(
                username=username, email=email, password_hash=password_hash
            )
        except IntegrityError as exc:
            raise DuplicateUserError(
                f"Username {username!r} or email {email!r} is already taken."
            ) from exc
        return UserRead.model_validate(user)

    async def authenticate(self, username: str, password: str) -> UserRead:
        """Verify credentials and return the matching user. `username` may be either a username
        or an email (matching `UserLogin`'s own field).

        Raises `InvalidCredentialsError` for both "no such user" and "wrong password" -- see
        that exception's own docstring for why the two must never be distinguishable to a
        caller. Raises `InactiveUserError` only once the password has already been confirmed
        correct -- an attacker who doesn't know the password learns nothing extra either way.
        """
        user = await self._repository.get_by_username(
            username
        ) or await self._repository.get_by_email(username)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Incorrect username/email or password.")
        if not user.is_active:
            raise InactiveUserError(f"The account {username!r} is inactive.")
        return UserRead.model_validate(user)

    async def create_token_pair(self, user_id: int) -> TokenPair:
        """Issue a fresh access + refresh token pair for `user_id`, persisting the refresh
        token's `jti`/`expires_at` so it can later be looked up and revoked.
        """
        subject = str(user_id)
        access_token = jwt_module.create_access_token(
            subject,
            secret_key=self._jwt_secret_key,
            algorithm=self._jwt_algorithm,
            expire_minutes=self._access_token_expire_minutes,
        )
        refresh_token, claims = jwt_module.create_refresh_token(
            subject,
            secret_key=self._jwt_secret_key,
            algorithm=self._jwt_algorithm,
            expire_days=self._refresh_token_expire_days,
        )
        await self._repository.store_refresh_token(
            user_id=user_id, jti=claims.jti, expires_at=claims.exp
        )
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    async def validate_refresh_token(self, refresh_token: str) -> RefreshToken:
        """Decode `refresh_token` and confirm it is still good: a `"refresh"`-type token, with
        a `jti` this server actually issued (`InvalidTokenError` otherwise), not revoked
        (`RefreshTokenRevokedError`), and not past the *stored* `expires_at`
        (`TokenExpiredError` -- checked independently of the JWT's own `exp`, which
        `jwt.validate_token` already checked; both are set to the same instant at issuance, so
        this is defense in depth, not a second, different policy).

        Returns the `RefreshToken` row itself -- `refresh_tokens`/`logout` both need its
        `jti`/`user_id`, not just a bool.
        """
        claims = jwt_module.validate_token(
            refresh_token,
            secret_key=self._jwt_secret_key,
            algorithm=self._jwt_algorithm,
            expected_type="refresh",
        )
        row = await self._repository.get_refresh_token(claims.jti)
        if row is None:
            raise InvalidTokenError("This refresh token was not issued by this server.")
        if row.revoked:
            raise RefreshTokenRevokedError("This refresh token has already been used or revoked.")
        if row.expires_at < datetime.now(UTC):
            raise TokenExpiredError("This refresh token has expired.")
        return row

    async def refresh_tokens(self, refresh_token: str) -> TokenPair:
        """Rotate `refresh_token` for a new access + refresh pair. The old refresh token is
        revoked as part of this call (rotation) -- it can never be used again, whether or not
        the new pair is ever used.
        """
        row = await self.validate_refresh_token(refresh_token)
        user = await self._repository.get_by_id(row.user_id)
        if user is None or not user.is_active:
            raise InactiveUserError("The account for this refresh token is no longer active.")
        await self._repository.revoke_refresh_token(row.jti)
        return await self.create_token_pair(user.id)

    async def logout(self, refresh_token: str) -> None:
        """Revoke `refresh_token`. Does not, and cannot, invalidate any access token already
        issued from it -- an access token is validated purely by signature and `exp`; it simply
        expires on its own, within `access_token_expire_minutes` of being issued (see
        `querymind.auth.cache`'s own docstring for why revoking one early is out of scope).
        """
        row = await self.validate_refresh_token(refresh_token)
        await self._repository.revoke_refresh_token(row.jti)

    async def get_current_user(self, access_token: str) -> UserRead:
        """Resolve the authenticated user from a raw access token.

        Added in Phase 22A Part 2, purely additively -- no existing method above changed. Part
        2's FastAPI integration needs exactly this ("no duplicated JWT logic, everything
        delegates to `AuthenticationService`"), and Part 1 had no equivalent: `validate_refresh_token`
        decodes a *refresh* token and returns the stored `RefreshToken` row; this decodes an
        *access* token (which has no stored row at all -- see `create_token_pair`'s own
        docstring) and resolves straight to the user it names.

        Raises `InvalidTokenError`/`TokenExpiredError` for a bad, wrong-type, or expired token,
        or `InactiveUserError` if the account has since been deactivated. Never
        `InvalidCredentialsError` -- that exception means "a login attempt's password was
        wrong," a different failure from "this already-issued token no longer resolves."
        """
        claims = jwt_module.validate_token(
            access_token,
            secret_key=self._jwt_secret_key,
            algorithm=self._jwt_algorithm,
            expected_type="access",
        )
        user = await self._repository.get_by_id(int(claims.sub))
        if user is None:
            raise InvalidTokenError("This token's subject no longer exists.")
        if not user.is_active:
            raise InactiveUserError("This account is no longer active.")
        return UserRead.model_validate(user)

    # -- Authorization (Phase 22B) ---------------------------------------------------------
    #
    # Everything below answers "what is this already-authenticated user allowed to do,"
    # never "who are they" -- pure, synchronous functions of a `UserRead` already resolved by
    # `get_current_user` above, no I/O, no new exception a caller could confuse with an
    # `AuthenticationError` (see `querymind.auth.exceptions`' own module docstring for why
    # `AuthorizationError` is a separate hierarchy). Kept as methods here, not free functions
    # elsewhere, so "no duplicated authorization logic inside routes" has exactly one place to
    # mean: every `Depends()` in `querymind.api.dependencies` that checks a role calls one of
    # these, never comparing `user.role` itself.

    def has_role(self, user: UserRead, role: UserRole) -> bool:
        """Exact match -- does `user` have precisely `role`? Informational (e.g. for a UI to
        decide what to show), not hierarchical -- see `require_role` for the ranked version
        used to actually gate an action.
        """
        return user.role is role

    def is_admin(self, user: UserRead) -> bool:
        """Shorthand for `has_role(user, UserRole.ADMIN)` -- the single most common check."""
        return self.has_role(user, UserRole.ADMIN)

    def require_role(self, user: UserRead, minimum_role: UserRole) -> None:
        """Enforce a *ranked* minimum: `ADMIN` (rank 3) satisfies a `minimum_role` of `ANALYST`
        (rank 2) or `VIEWER` (rank 1); `ANALYST` satisfies `ANALYST`/`VIEWER` but not `ADMIN`;
        `VIEWER` satisfies only `VIEWER`. Raises `ForbiddenRoleError` otherwise -- this is the
        method every `RequireAdmin`/`RequireAnalyst`/`RequireViewer` dependency calls.
        """
        if _ROLE_RANK[user.role] < _ROLE_RANK[minimum_role]:
            raise ForbiddenRoleError(
                f"This action requires at least the {minimum_role.value!r} role; "
                f"the current user has {user.role.value!r}."
            )

    def require_any_role(self, user: UserRead, *roles: UserRole) -> None:
        """Enforce exact-set membership, no rank/hierarchy involved -- for a combination of
        roles the rank order alone can't express (e.g. "ADMIN or VIEWER, but not ANALYST").
        Raises `InsufficientPermissionsError` otherwise. `RequireAnyRole(...)`
        (`querymind.api.dependencies`) is the one caller.
        """
        if user.role not in roles:
            allowed = ", ".join(role.value for role in roles)
            raise InsufficientPermissionsError(
                f"This action requires one of the following roles: {allowed}; "
                f"the current user has {user.role.value!r}."
            )
