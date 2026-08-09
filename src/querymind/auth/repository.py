"""`AuthenticationRepository` -- persistence only, no business logic.

Every method does exactly one mechanical thing against the database: look a row up, insert one,
or flip a column. Nothing here decides whether an operation is *allowed* (a duplicate username,
a wrong password, a revoked token) -- that is `AuthenticationService`'s job entirely; this class
would insert a duplicate username without complaint if the database's own unique constraint
didn't stop it (see `AuthenticationService.register_user`'s own docstring for how that
constraint's `IntegrityError` gets translated into a domain-meaningful outcome one layer up).

Takes an `async_sessionmaker`, not a live `AsyncSession` -- mirrors
`querymind.sql_execution.connection.DatabaseConnectionProvider`'s "hold the process-scoped
factory, acquire a short-lived resource per call" shape exactly, which is what lets this class
be constructed once (Phase 22A Part 2's `ApplicationContainer`) rather than per-request.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from querymind.auth.models import RefreshToken, User
from querymind.db.session import transactional_session


class AuthenticationRepository:
    """Persistence for `User`/`RefreshToken` -- see module docstring."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_user(
        self, *, username: str, email: str, password_hash: str, is_superuser: bool = False
    ) -> User:
        """Insert a new `User` row. Raises `sqlalchemy.exc.IntegrityError` unchanged if
        `username`/`email` already exists -- translating that into `DuplicateUserError` is
        `AuthenticationService.register_user`'s job, not this method's.
        """
        async with transactional_session(self._session_factory) as session:
            user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                is_superuser=is_superuser,
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def get_by_username(self, username: str) -> User | None:
        async with transactional_session(self._session_factory) as session:
            result = await session.execute(select(User).where(User.username == username))
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        async with transactional_session(self._session_factory) as session:
            result = await session.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        async with transactional_session(self._session_factory) as session:
            return await session.get(User, user_id)

    async def store_refresh_token(
        self, *, user_id: int, jti: str, expires_at: datetime
    ) -> RefreshToken:
        async with transactional_session(self._session_factory) as session:
            refresh_token = RefreshToken(user_id=user_id, jti=jti, expires_at=expires_at)
            session.add(refresh_token)
            await session.flush()
            await session.refresh(refresh_token)
            return refresh_token

    async def get_refresh_token(self, jti: str) -> RefreshToken | None:
        async with transactional_session(self._session_factory) as session:
            result = await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
            return result.scalar_one_or_none()

    async def revoke_refresh_token(self, jti: str) -> None:
        """No-op if `jti` doesn't exist -- callers that need to know whether a token exists at
        all call `get_refresh_token` first (see `AuthenticationService.validate_refresh_token`).
        """
        async with transactional_session(self._session_factory) as session:
            result = await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
            refresh_token = result.scalar_one_or_none()
            if refresh_token is not None:
                refresh_token.revoked = True
