"""Unit tests for `AuthenticationService` -- every business rule this phase adds, against an
in-memory fake repository (`_FakeAuthenticationRepository` below), never a real database. This
is deliberate, not a shortcut: `AuthenticationService` is defined (Phase 22A Part 1's own
constraint) to have no FastAPI/HTTP awareness and no direct database access of its own -- its
only collaborator is `AuthenticationRepository`, so a fake implementing that same interface
exercises every real code path in the service with no I/O at all. `test_integration.py` is what
proves the service also works against the real `AuthenticationRepository`/Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from querymind.auth.exceptions import (
    DuplicateUserError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)
from querymind.auth.jwt import create_access_token, decode_token
from querymind.auth.models import RefreshToken, User
from querymind.auth.service import AuthenticationService
from tests.auth.conftest import TEST_JWT_SECRET_KEY


@dataclass
class _FakeAuthenticationRepository:
    """An in-memory stand-in for `AuthenticationRepository`, implementing the exact same async
    interface (including raising `IntegrityError` on a genuine unique-constraint violation, the
    one behavior `AuthenticationService.register_user` depends on from its repository).
    """

    users: dict[int, User] = field(default_factory=dict)
    refresh_tokens: dict[str, RefreshToken] = field(default_factory=dict)
    _next_user_id: int = 1
    _next_refresh_token_id: int = 1

    async def create_user(
        self, *, username: str, email: str, password_hash: str, is_superuser: bool = False
    ) -> User:
        if any(u.username == username or u.email == email for u in self.users.values()):
            raise IntegrityError("duplicate", params=None, orig=Exception("duplicate"))
        user = User(
            username=username, email=email, password_hash=password_hash, is_superuser=is_superuser
        )
        user.id = self._next_user_id
        user.is_active = True
        user.created_at = datetime.now(UTC)
        user.updated_at = datetime.now(UTC)
        self._next_user_id += 1
        self.users[user.id] = user
        return user

    async def get_by_username(self, username: str) -> User | None:
        return next((u for u in self.users.values() if u.username == username), None)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email), None)

    async def get_by_id(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    async def store_refresh_token(
        self, *, user_id: int, jti: str, expires_at: datetime
    ) -> RefreshToken:
        refresh_token = RefreshToken(user_id=user_id, jti=jti, expires_at=expires_at)
        refresh_token.id = self._next_refresh_token_id
        refresh_token.revoked = False
        refresh_token.created_at = datetime.now(UTC)
        self._next_refresh_token_id += 1
        self.refresh_tokens[jti] = refresh_token
        return refresh_token

    async def get_refresh_token(self, jti: str) -> RefreshToken | None:
        return self.refresh_tokens.get(jti)

    async def revoke_refresh_token(self, jti: str) -> None:
        token = self.refresh_tokens.get(jti)
        if token is not None:
            token.revoked = True


@pytest.fixture
def repository() -> _FakeAuthenticationRepository:
    return _FakeAuthenticationRepository()


@pytest.fixture
def service(repository: _FakeAuthenticationRepository) -> AuthenticationService:
    return AuthenticationService(repository, jwt_secret_key=TEST_JWT_SECRET_KEY)  # type: ignore[arg-type]


class TestRegisterUser:
    async def test_creates_a_user_with_a_hashed_password(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="alice", email="alice@example.com", password="password123"
        )

        assert user.username == "alice"
        stored = repository.users[user.id]
        assert stored.password_hash != "password123"
        assert stored.password_hash.startswith("$argon2")

    async def test_returns_a_user_read_never_the_password_hash(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="bob", email="bob@example.com", password="password123"
        )
        assert not hasattr(user, "password_hash")

    async def test_rejects_a_duplicate_username(self, service: AuthenticationService) -> None:
        await service.register_user(
            username="carol", email="carol1@example.com", password="password123"
        )

        with pytest.raises(DuplicateUserError):
            await service.register_user(
                username="carol", email="carol2@example.com", password="password123"
            )

    async def test_rejects_a_duplicate_email(self, service: AuthenticationService) -> None:
        await service.register_user(
            username="dave1", email="dave@example.com", password="password123"
        )

        with pytest.raises(DuplicateUserError):
            await service.register_user(
                username="dave2", email="dave@example.com", password="password123"
            )

    async def test_a_race_at_insert_time_still_raises_duplicate_user_error(
        self, repository: _FakeAuthenticationRepository
    ) -> None:
        """Simulates two concurrent registrations both passing the pre-check before either has
        inserted -- the *second* insert must still surface as `DuplicateUserError`, via the
        `IntegrityError` catch, not an unhandled `IntegrityError`. See
        `AuthenticationService.register_user`'s own docstring for why both checks exist.
        """

        class _RacyRepository(_FakeAuthenticationRepository):
            async def get_by_username(self, username: str) -> User | None:
                return None  # pretend the pre-check always finds nothing

            async def get_by_email(self, email: str) -> User | None:
                return None

        racy_repository = _RacyRepository()
        await racy_repository.create_user(
            username="erin", email="erin@example.com", password_hash="hash"
        )
        service = AuthenticationService(racy_repository, jwt_secret_key=TEST_JWT_SECRET_KEY)  # type: ignore[arg-type]

        with pytest.raises(DuplicateUserError):
            await service.register_user(
                username="erin", email="erin@example.com", password="password123"
            )


class TestAuthenticate:
    async def test_succeeds_with_the_correct_username_and_password(
        self, service: AuthenticationService
    ) -> None:
        await service.register_user(
            username="frank", email="frank@example.com", password="password123"
        )

        user = await service.authenticate("frank", "password123")

        assert user.username == "frank"

    async def test_succeeds_looking_up_by_email_instead_of_username(
        self, service: AuthenticationService
    ) -> None:
        await service.register_user(
            username="gina", email="gina@example.com", password="password123"
        )

        user = await service.authenticate("gina@example.com", "password123")

        assert user.username == "gina"

    async def test_fails_for_an_unknown_username(self, service: AuthenticationService) -> None:
        with pytest.raises(InvalidCredentialsError):
            await service.authenticate("nobody", "whatever")

    async def test_fails_for_the_wrong_password(self, service: AuthenticationService) -> None:
        await service.register_user(
            username="hank", email="hank@example.com", password="password123"
        )

        with pytest.raises(InvalidCredentialsError):
            await service.authenticate("hank", "wrong-password")

    async def test_fails_for_an_inactive_user_even_with_the_right_password(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="ivy", email="ivy@example.com", password="password123"
        )
        repository.users[user.id].is_active = False

        with pytest.raises(InactiveUserError):
            await service.authenticate("ivy", "password123")


class TestCreateTokenPair:
    async def test_issues_an_access_and_a_refresh_token(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="jack", email="jack@example.com", password="password123"
        )

        tokens = await service.create_token_pair(user.id)

        assert tokens.token_type == "bearer"
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.access_token != tokens.refresh_token

    async def test_the_access_token_carries_the_user_id_as_subject(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="kate", email="kate@example.com", password="password123"
        )

        tokens = await service.create_token_pair(user.id)

        claims = decode_token(tokens.access_token, secret_key=TEST_JWT_SECRET_KEY)
        assert claims.sub == str(user.id)
        assert claims.type == "access"

    async def test_persists_the_refresh_token(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="leo", email="leo@example.com", password="password123"
        )

        tokens = await service.create_token_pair(user.id)

        claims = decode_token(tokens.refresh_token, secret_key=TEST_JWT_SECRET_KEY)
        assert claims.jti in repository.refresh_tokens
        assert repository.refresh_tokens[claims.jti].user_id == user.id


class TestValidateRefreshToken:
    async def test_returns_the_stored_row_for_a_valid_token(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="mia", email="mia@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)

        row = await service.validate_refresh_token(tokens.refresh_token)

        assert row.user_id == user.id
        assert row.revoked is False

    async def test_rejects_an_access_token(self, service: AuthenticationService) -> None:
        user = await service.register_user(
            username="noah", email="noah@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)

        with pytest.raises(InvalidTokenError):
            await service.validate_refresh_token(tokens.access_token)

    async def test_rejects_a_refresh_token_this_server_never_issued(
        self, service: AuthenticationService
    ) -> None:
        foreign_token = create_access_token(
            "1", secret_key=TEST_JWT_SECRET_KEY
        )  # wrong type AND unknown jti either way
        with pytest.raises(InvalidTokenError):
            await service.validate_refresh_token(foreign_token)

    async def test_rejects_a_revoked_refresh_token(self, service: AuthenticationService) -> None:
        user = await service.register_user(
            username="olga", email="olga@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)
        await service.logout(tokens.refresh_token)

        with pytest.raises(RefreshTokenRevokedError):
            await service.validate_refresh_token(tokens.refresh_token)

    async def test_rejects_a_refresh_token_expired_in_storage(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="pete", email="pete@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)
        claims = decode_token(tokens.refresh_token, secret_key=TEST_JWT_SECRET_KEY)
        repository.refresh_tokens[claims.jti].expires_at = datetime.now(UTC) - timedelta(seconds=1)

        with pytest.raises(TokenExpiredError):
            await service.validate_refresh_token(tokens.refresh_token)


class TestRefreshTokens:
    async def test_returns_a_new_token_pair(self, service: AuthenticationService) -> None:
        user = await service.register_user(
            username="quinn", email="quinn@example.com", password="password123"
        )
        original = await service.create_token_pair(user.id)

        rotated = await service.refresh_tokens(original.refresh_token)

        assert rotated.access_token != original.access_token
        assert rotated.refresh_token != original.refresh_token

    async def test_revokes_the_old_refresh_token(self, service: AuthenticationService) -> None:
        user = await service.register_user(
            username="ruth", email="ruth@example.com", password="password123"
        )
        original = await service.create_token_pair(user.id)

        await service.refresh_tokens(original.refresh_token)

        with pytest.raises(RefreshTokenRevokedError):
            await service.validate_refresh_token(original.refresh_token)

    async def test_the_old_refresh_token_cannot_be_reused_after_rotation(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="sam", email="sam@example.com", password="password123"
        )
        original = await service.create_token_pair(user.id)
        await service.refresh_tokens(original.refresh_token)

        with pytest.raises(RefreshTokenRevokedError):
            await service.refresh_tokens(original.refresh_token)

    async def test_rejects_refresh_for_a_now_inactive_user(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="tina", email="tina@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)
        repository.users[user.id].is_active = False

        with pytest.raises(InactiveUserError):
            await service.refresh_tokens(tokens.refresh_token)


class TestLogout:
    async def test_revokes_the_refresh_token(self, service: AuthenticationService) -> None:
        user = await service.register_user(
            username="uma", email="uma@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)

        await service.logout(tokens.refresh_token)

        with pytest.raises(RefreshTokenRevokedError):
            await service.validate_refresh_token(tokens.refresh_token)

    async def test_logging_out_twice_raises_refresh_token_revoked_error(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="vince", email="vince@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)
        await service.logout(tokens.refresh_token)

        with pytest.raises(RefreshTokenRevokedError):
            await service.logout(tokens.refresh_token)

    async def test_does_not_invalidate_the_access_token(
        self, service: AuthenticationService
    ) -> None:
        # An access token is validated purely by signature/exp -- logout only revokes the
        # refresh token (see AuthenticationService.logout's own docstring).
        user = await service.register_user(
            username="wade", email="wade@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)

        await service.logout(tokens.refresh_token)

        claims = decode_token(tokens.access_token, secret_key=TEST_JWT_SECRET_KEY)
        assert claims.sub == str(user.id)
