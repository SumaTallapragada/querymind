"""Unit tests for `querymind.auth.exceptions`' hierarchy -- every subclass really is an
`AuthenticationError`, and every subclass is distinguishable from every other, so a caller
catching one specific type never accidentally also catches a different failure mode.
"""

from __future__ import annotations

import pytest

from querymind.auth.exceptions import (
    AuthenticationError,
    DuplicateUserError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenRevokedError,
    TokenExpiredError,
)

_SUBCLASSES = (
    InvalidCredentialsError,
    InactiveUserError,
    DuplicateUserError,
    InvalidTokenError,
    TokenExpiredError,
    RefreshTokenRevokedError,
)


class TestHierarchy:
    @pytest.mark.parametrize("exc_type", _SUBCLASSES)
    def test_every_subclass_is_an_authentication_error(self, exc_type: type[Exception]) -> None:
        assert issubclass(exc_type, AuthenticationError)

    @pytest.mark.parametrize("exc_type", _SUBCLASSES)
    def test_every_subclass_is_a_plain_exception(self, exc_type: type[Exception]) -> None:
        assert issubclass(exc_type, Exception)

    def test_authentication_error_itself_is_catchable_as_a_plain_exception(self) -> None:
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("boom")

    @pytest.mark.parametrize("exc_type", _SUBCLASSES)
    def test_each_subclass_is_catchable_by_the_base_class(self, exc_type: type[Exception]) -> None:
        with pytest.raises(AuthenticationError):
            raise exc_type("boom")

    def test_subclasses_are_mutually_distinct(self) -> None:
        assert len(set(_SUBCLASSES)) == len(_SUBCLASSES)
        for exc_type in _SUBCLASSES:
            others = [other for other in _SUBCLASSES if other is not exc_type]
            assert not any(issubclass(exc_type, other) for other in others)


class TestMessages:
    @pytest.mark.parametrize("exc_type", _SUBCLASSES)
    def test_carries_its_constructor_message(self, exc_type: type[Exception]) -> None:
        exc = exc_type("a specific, human-readable reason")
        assert str(exc) == "a specific, human-readable reason"
