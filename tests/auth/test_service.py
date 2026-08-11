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
    ApiKeyExpiredError,
    ApiKeyNotFoundError,
    ApiKeyRevokedError,
    DuplicateUserError,
    ForbiddenRoleError,
    InactiveUserError,
    InsufficientPermissionsError,
    InvalidApiKeyError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)
from querymind.auth.jwt import create_access_token, decode_token
from querymind.auth.models import ApiKey, RefreshToken, User, UserRole
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
    api_keys: dict[int, ApiKey] = field(default_factory=dict)
    _next_user_id: int = 1
    _next_refresh_token_id: int = 1
    _next_api_key_id: int = 1

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
        user.role = UserRole.ANALYST
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

    async def create_api_key(
        self,
        *,
        user_id: int,
        key_prefix: str,
        key_hash: str,
        name: str,
        expires_at: datetime | None,
    ) -> ApiKey:
        api_key = ApiKey(
            user_id=user_id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            name=name,
            expires_at=expires_at,
        )
        api_key.id = self._next_api_key_id
        api_key.last_used_at = None
        api_key.revoked_at = None
        api_key.created_at = datetime.now(UTC)
        self._next_api_key_id += 1
        self.api_keys[api_key.id] = api_key
        return api_key

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        return next((key for key in self.api_keys.values() if key.key_hash == key_hash), None)

    async def get_api_key_by_id(self, key_id: int) -> ApiKey | None:
        return self.api_keys.get(key_id)

    async def list_api_keys_for_user(self, user_id: int) -> list[ApiKey]:
        return sorted(
            (key for key in self.api_keys.values() if key.user_id == user_id),
            key=lambda key: key.created_at,
            reverse=True,
        )

    async def revoke_api_key(self, key_id: int) -> None:
        key = self.api_keys.get(key_id)
        if key is not None and key.revoked_at is None:
            key.revoked_at = datetime.now(UTC)

    async def touch_api_key_last_used(self, key_id: int) -> None:
        key = self.api_keys.get(key_id)
        if key is not None:
            key.last_used_at = datetime.now(UTC)


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


class TestGetCurrentUser:
    """Phase 22A Part 2 addition -- see `AuthenticationService.get_current_user`'s own docstring
    for why this method exists (Part 1 had no equivalent for access tokens).
    """

    async def test_resolves_the_user_for_a_valid_access_token(
        self, service: AuthenticationService
    ) -> None:
        registered = await service.register_user(
            username="xena", email="xena@example.com", password="password123"
        )
        tokens = await service.create_token_pair(registered.id)

        resolved = await service.get_current_user(tokens.access_token)

        assert resolved.id == registered.id
        assert resolved.username == "xena"

    async def test_rejects_a_refresh_token_presented_as_access(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="yara", email="yara@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)

        with pytest.raises(InvalidTokenError):
            await service.get_current_user(tokens.refresh_token)

    async def test_rejects_a_token_with_a_wrong_signature(
        self, service: AuthenticationService
    ) -> None:
        foreign_token = create_access_token(
            "999999", secret_key="a-completely-different-secret-of-sufficient-length"
        )
        with pytest.raises(InvalidTokenError):
            await service.get_current_user(foreign_token)

    async def test_rejects_a_token_whose_subject_no_longer_exists(
        self, service: AuthenticationService
    ) -> None:
        never_registered_user_id = "424242"
        token = create_access_token(never_registered_user_id, secret_key=TEST_JWT_SECRET_KEY)

        with pytest.raises(InvalidTokenError):
            await service.get_current_user(token)

    async def test_rejects_a_token_for_a_now_inactive_user(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="zane", email="zane@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)
        repository.users[user.id].is_active = False

        with pytest.raises(InactiveUserError):
            await service.get_current_user(tokens.access_token)

    async def test_never_leaks_the_password_hash(self, service: AuthenticationService) -> None:
        user = await service.register_user(
            username="amos", email="amos@example.com", password="password123"
        )
        tokens = await service.create_token_pair(user.id)

        resolved = await service.get_current_user(tokens.access_token)

        assert not hasattr(resolved, "password_hash")


# -- Authorization (Phase 22B) -------------------------------------------------------------
#
# `has_role`/`is_admin`/`require_role`/`require_any_role` are pure functions of an already-
# resolved `UserRead` -- no repository call, no I/O -- so these tests exercise them directly
# against `UserRead.model_copy(update={"role": ...})` variants of a single registered user,
# rather than registering a fresh user per role the way `TestRegisterUser`/`TestAuthenticate`
# above need to (those methods' behavior genuinely depends on what's in the repository; these
# don't).


class TestHasRole:
    async def test_true_for_an_exact_match(self, service: AuthenticationService) -> None:
        user = (
            await service.register_user(
                username="role_alice", email="role_alice@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ANALYST})

        assert service.has_role(user, UserRole.ANALYST) is True

    async def test_false_for_a_higher_ranked_role(self, service: AuthenticationService) -> None:
        """Not hierarchical -- an `ADMIN` does not `has_role(..., VIEWER)`, unlike `require_role`."""
        user = (
            await service.register_user(
                username="role_bob", email="role_bob@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ADMIN})

        assert service.has_role(user, UserRole.VIEWER) is False


class TestIsAdmin:
    async def test_true_for_an_admin(self, service: AuthenticationService) -> None:
        user = (
            await service.register_user(
                username="role_carol", email="role_carol@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ADMIN})

        assert service.is_admin(user) is True

    async def test_false_for_a_non_admin(self, service: AuthenticationService) -> None:
        user = (
            await service.register_user(
                username="role_dave", email="role_dave@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ANALYST})

        assert service.is_admin(user) is False


class TestRequireRole:
    async def test_an_exact_match_passes(self, service: AuthenticationService) -> None:
        user = (
            await service.register_user(
                username="role_erin", email="role_erin@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ANALYST})

        service.require_role(user, UserRole.ANALYST)  # does not raise

    async def test_a_higher_ranked_role_satisfies_a_lower_minimum(
        self, service: AuthenticationService
    ) -> None:
        """`ADMIN` (rank 3) satisfies a `minimum_role` of `ANALYST` (rank 2) -- the ranked
        behavior `RequireAnalyst`/`RequireViewer` (`querymind.api.dependencies`) rely on to let
        an `ADMIN` reach an `ANALYST`-gated route.
        """
        user = (
            await service.register_user(
                username="role_frank", email="role_frank@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ADMIN})

        service.require_role(user, UserRole.ANALYST)  # does not raise

    async def test_a_lower_ranked_role_raises_forbidden_role_error(
        self, service: AuthenticationService
    ) -> None:
        user = (
            await service.register_user(
                username="role_gina", email="role_gina@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.VIEWER})

        with pytest.raises(ForbiddenRoleError):
            service.require_role(user, UserRole.ADMIN)


class TestRequireAnyRole:
    async def test_a_role_in_the_set_passes(self, service: AuthenticationService) -> None:
        user = (
            await service.register_user(
                username="role_hank", email="role_hank@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.VIEWER})

        service.require_any_role(user, UserRole.ADMIN, UserRole.VIEWER)  # does not raise

    async def test_not_hierarchical_a_higher_rank_outside_the_set_still_fails(
        self, service: AuthenticationService
    ) -> None:
        """Unlike `require_role`, `require_any_role` is exact-set membership -- an `ADMIN` does
        not automatically satisfy `require_any_role(user, VIEWER)`.
        """
        user = (
            await service.register_user(
                username="role_ivy", email="role_ivy@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ADMIN})

        with pytest.raises(InsufficientPermissionsError):
            service.require_any_role(user, UserRole.VIEWER)

    async def test_a_role_outside_the_set_raises_insufficient_permissions_error(
        self, service: AuthenticationService
    ) -> None:
        user = (
            await service.register_user(
                username="role_jack", email="role_jack@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ANALYST})

        with pytest.raises(InsufficientPermissionsError):
            service.require_any_role(user, UserRole.ADMIN, UserRole.VIEWER)


# -- API keys (Phase 22D) -------------------------------------------------------------------


class TestCreateApiKey:
    async def test_returns_the_raw_key_and_its_metadata(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="key_alice", email="key_alice@example.com", password="password123"
        )

        created = await service.create_api_key(user_id=user.id, name="CI pipeline")

        assert created.raw_key.startswith("qm_")
        assert created.key.name == "CI pipeline"
        assert created.key.revoked_at is None
        assert created.key.last_used_at is None

    async def test_only_the_hash_is_persisted_never_the_raw_key(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="key_bob", email="key_bob@example.com", password="password123"
        )

        created = await service.create_api_key(user_id=user.id, name="laptop")

        stored = repository.api_keys[created.key.id]
        assert stored.key_hash != created.raw_key
        assert created.raw_key not in stored.key_hash

    async def test_two_keys_for_the_same_user_are_independent(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="key_carol", email="key_carol@example.com", password="password123"
        )

        first = await service.create_api_key(user_id=user.id, name="one")
        second = await service.create_api_key(user_id=user.id, name="two")

        assert first.raw_key != second.raw_key
        assert first.key.id != second.key.id


class TestAuthenticateApiKey:
    async def test_resolves_the_owning_user(self, service: AuthenticationService) -> None:
        user = await service.register_user(
            username="key_dave", email="key_dave@example.com", password="password123"
        )
        created = await service.create_api_key(user_id=user.id, name="resolves")

        resolved = await service.authenticate_api_key(created.raw_key)

        assert resolved.id == user.id
        assert resolved.username == "key_dave"

    async def test_inherits_the_owners_role_exactly(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        """A key cannot escalate privileges: it resolves to whatever role the owning `User` row
        has *at authentication time*, not a role fixed at key-creation time -- if the owner is
        later promoted or demoted, every one of their keys reflects that immediately, the same
        way a JWT already does via `get_current_user`.
        """
        user = await service.register_user(
            username="key_erin", email="key_erin@example.com", password="password123"
        )
        created = await service.create_api_key(user_id=user.id, name="role test")
        repository.users[user.id].role = UserRole.ADMIN

        resolved = await service.authenticate_api_key(created.raw_key)

        assert resolved.role is UserRole.ADMIN

    async def test_rejects_a_malformed_key(self, service: AuthenticationService) -> None:
        with pytest.raises(InvalidApiKeyError):
            await service.authenticate_api_key("not-a-real-key")

    async def test_rejects_a_well_formed_but_unknown_key(
        self, service: AuthenticationService
    ) -> None:
        with pytest.raises(InvalidApiKeyError):
            await service.authenticate_api_key("qm_" + "a" * 40)

    async def test_rejects_a_revoked_key(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="key_frank", email="key_frank@example.com", password="password123"
        )
        created = await service.create_api_key(user_id=user.id, name="to revoke")
        await service.revoke_api_key(requesting_user=user, key_id=created.key.id)

        with pytest.raises(ApiKeyRevokedError):
            await service.authenticate_api_key(created.raw_key)

    async def test_rejects_an_expired_key(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="key_gina", email="key_gina@example.com", password="password123"
        )
        created = await service.create_api_key(
            user_id=user.id, name="expired", expires_at=datetime.now(UTC) - timedelta(seconds=1)
        )

        with pytest.raises(ApiKeyExpiredError):
            await service.authenticate_api_key(created.raw_key)

    async def test_rejects_a_key_for_a_now_inactive_user(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="key_hank", email="key_hank@example.com", password="password123"
        )
        created = await service.create_api_key(user_id=user.id, name="deactivated owner")
        repository.users[user.id].is_active = False

        with pytest.raises(InactiveUserError):
            await service.authenticate_api_key(created.raw_key)

    async def test_touches_last_used_at_on_success(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="key_ivy", email="key_ivy@example.com", password="password123"
        )
        created = await service.create_api_key(user_id=user.id, name="touch test")
        assert repository.api_keys[created.key.id].last_used_at is None

        await service.authenticate_api_key(created.raw_key)

        assert repository.api_keys[created.key.id].last_used_at is not None

    async def test_does_not_re_touch_last_used_at_within_the_throttle_window(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="key_jack", email="key_jack@example.com", password="password123"
        )
        created = await service.create_api_key(user_id=user.id, name="throttle test")
        recent = datetime.now(UTC) - timedelta(seconds=1)
        repository.api_keys[created.key.id].last_used_at = recent

        await service.authenticate_api_key(created.raw_key)

        assert repository.api_keys[created.key.id].last_used_at == recent


class TestListApiKeys:
    async def test_returns_only_the_given_users_keys(self, service: AuthenticationService) -> None:
        owner = await service.register_user(
            username="key_kate", email="key_kate@example.com", password="password123"
        )
        other = await service.register_user(
            username="key_liam", email="key_liam@example.com", password="password123"
        )
        await service.create_api_key(user_id=owner.id, name="mine")
        await service.create_api_key(user_id=other.id, name="not mine")

        keys = await service.list_api_keys(owner.id)

        assert [key.name for key in keys] == ["mine"]

    async def test_never_includes_a_hash_or_raw_key(self, service: AuthenticationService) -> None:
        user = await service.register_user(
            username="key_mia", email="key_mia@example.com", password="password123"
        )
        await service.create_api_key(user_id=user.id, name="metadata only")

        keys = await service.list_api_keys(user.id)

        assert not hasattr(keys[0], "key_hash")


class TestRevokeApiKey:
    async def test_the_owner_can_revoke_their_own_key(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="key_noah", email="key_noah@example.com", password="password123"
        )
        created = await service.create_api_key(user_id=user.id, name="mine")

        await service.revoke_api_key(requesting_user=user, key_id=created.key.id)

        assert repository.api_keys[created.key.id].revoked_at is not None

    async def test_an_admin_can_revoke_another_users_key(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        owner = await service.register_user(
            username="key_olive", email="key_olive@example.com", password="password123"
        )
        admin = (
            await service.register_user(
                username="key_admin", email="key_admin@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ADMIN})
        created = await service.create_api_key(user_id=owner.id, name="owned by olive")

        await service.revoke_api_key(requesting_user=admin, key_id=created.key.id)

        assert repository.api_keys[created.key.id].revoked_at is not None

    async def test_a_non_owner_non_admin_cannot_revoke_someone_elses_key(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        owner = await service.register_user(
            username="key_paul", email="key_paul@example.com", password="password123"
        )
        stranger = (
            await service.register_user(
                username="key_stranger", email="key_stranger@example.com", password="password123"
            )
        ).model_copy(update={"role": UserRole.ANALYST})
        created = await service.create_api_key(user_id=owner.id, name="owned by paul")

        with pytest.raises(ApiKeyNotFoundError):
            await service.revoke_api_key(requesting_user=stranger, key_id=created.key.id)
        assert repository.api_keys[created.key.id].revoked_at is None

    async def test_revoking_an_unknown_key_id_raises_not_found(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="key_quinn", email="key_quinn@example.com", password="password123"
        )

        with pytest.raises(ApiKeyNotFoundError):
            await service.revoke_api_key(requesting_user=user, key_id=999_999_999)

    async def test_revoking_an_already_revoked_key_is_idempotent(
        self, service: AuthenticationService
    ) -> None:
        user = await service.register_user(
            username="key_ruth", email="key_ruth@example.com", password="password123"
        )
        created = await service.create_api_key(user_id=user.id, name="double revoke")
        await service.revoke_api_key(requesting_user=user, key_id=created.key.id)

        await service.revoke_api_key(requesting_user=user, key_id=created.key.id)  # must not raise


class TestApiKeyCannotEscalateOrSelfPropagate:
    """The two guarantees the approved design specifically calls out: a key is capped at its
    owner's role (never higher), and using a key cannot itself create another key -- the latter
    is enforced at the API layer (`CurrentUserJwtOnly`, `tests/api/test_api_keys.py`), not here;
    this class proves the service-layer half: nothing about `authenticate_api_key`'s result is
    distinguishable from a JWT-resolved `UserRead`, so no code path downstream can even tell the
    difference to grant it more.
    """

    async def test_a_viewers_key_resolves_to_viewer_never_more(
        self, service: AuthenticationService, repository: _FakeAuthenticationRepository
    ) -> None:
        user = await service.register_user(
            username="key_sam", email="key_sam@example.com", password="password123"
        )
        repository.users[user.id].role = UserRole.VIEWER
        created = await service.create_api_key(user_id=user.id, name="viewer key")

        resolved = await service.authenticate_api_key(created.raw_key)

        assert resolved.role is UserRole.VIEWER
        with pytest.raises(ForbiddenRoleError):
            service.require_role(resolved, UserRole.ADMIN)
