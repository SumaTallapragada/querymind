"""Unit tests for `querymind.auth.jwt` -- token issuance, decoding, and type validation. No
database, no `AuthenticationService` -- pure encode/decode round trips against a fixed test
secret (`tests/auth/conftest.py`'s `TEST_JWT_SECRET_KEY`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from querymind.auth.exceptions import InvalidTokenError, TokenExpiredError
from querymind.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_token,
)
from tests.auth.conftest import TEST_JWT_SECRET_KEY

SECRET = TEST_JWT_SECRET_KEY


class TestCreateAccessToken:
    def test_decodes_back_to_the_same_subject(self) -> None:
        token = create_access_token("42", secret_key=SECRET)
        assert decode_token(token, secret_key=SECRET).sub == "42"

    def test_is_typed_access(self) -> None:
        token = create_access_token("1", secret_key=SECRET)
        assert decode_token(token, secret_key=SECRET).type == "access"

    def test_has_a_unique_jti_per_call(self) -> None:
        first = decode_token(create_access_token("1", secret_key=SECRET), secret_key=SECRET)
        second = decode_token(create_access_token("1", secret_key=SECRET), secret_key=SECRET)
        assert first.jti != second.jti

    def test_expires_after_the_configured_number_of_minutes(self) -> None:
        token = create_access_token("1", secret_key=SECRET, expire_minutes=30)
        claims = decode_token(token, secret_key=SECRET)
        assert claims.exp - claims.iat == timedelta(minutes=30)

    def test_defaults_to_thirty_minutes(self) -> None:
        token = create_access_token("1", secret_key=SECRET)
        claims = decode_token(token, secret_key=SECRET)
        assert claims.exp - claims.iat == timedelta(minutes=30)


class TestCreateRefreshToken:
    def test_returns_the_token_and_its_own_matching_claims(self) -> None:
        token, claims = create_refresh_token("7", secret_key=SECRET)
        assert claims.sub == "7"
        assert claims.type == "refresh"
        decoded = decode_token(token, secret_key=SECRET)
        assert decoded.jti == claims.jti
        assert decoded.sub == claims.sub
        assert decoded.exp == claims.exp

    def test_expires_after_the_configured_number_of_days(self) -> None:
        _, claims = create_refresh_token("1", secret_key=SECRET, expire_days=14)
        assert claims.exp - claims.iat == timedelta(days=14)

    def test_defaults_to_fourteen_days(self) -> None:
        _, claims = create_refresh_token("1", secret_key=SECRET)
        assert claims.exp - claims.iat == timedelta(days=14)


class TestDecodeToken:
    def test_raises_invalid_token_error_for_a_wrong_secret(self) -> None:
        token = create_access_token("1", secret_key=SECRET)
        with pytest.raises(InvalidTokenError):
            decode_token(token, secret_key="a-completely-different-secret-of-sufficient-length")

    def test_raises_invalid_token_error_for_garbage_input(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_token("not-a-jwt-at-all", secret_key=SECRET)

    def test_raises_token_expired_error_for_an_already_expired_token(self) -> None:
        token = create_access_token("1", secret_key=SECRET, expire_minutes=-1)
        with pytest.raises(TokenExpiredError):
            decode_token(token, secret_key=SECRET)

    def test_raises_invalid_token_error_when_a_required_claim_is_missing(self) -> None:
        now = datetime.now(UTC)
        payload = {
            "sub": "1",
            "jti": "missing-type-claim",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        token = pyjwt.encode(payload, SECRET, algorithm="HS256")

        with pytest.raises(InvalidTokenError):
            decode_token(token, secret_key=SECRET)

    def test_raises_invalid_token_error_for_a_different_algorithm(self) -> None:
        # Encoded with a different (but still HMAC) algorithm than decode_token expects.
        token = create_access_token("1", secret_key=SECRET, algorithm="HS384")
        with pytest.raises(InvalidTokenError):
            decode_token(token, secret_key=SECRET, algorithm="HS256")


class TestValidateToken:
    def test_accepts_an_access_token_when_access_is_expected(self) -> None:
        token = create_access_token("1", secret_key=SECRET)
        claims = validate_token(token, secret_key=SECRET, expected_type="access")
        assert claims.type == "access"

    def test_accepts_a_refresh_token_when_refresh_is_expected(self) -> None:
        token, _ = create_refresh_token("1", secret_key=SECRET)
        claims = validate_token(token, secret_key=SECRET, expected_type="refresh")
        assert claims.type == "refresh"

    def test_rejects_a_refresh_token_presented_as_access(self) -> None:
        token, _ = create_refresh_token("1", secret_key=SECRET)
        with pytest.raises(InvalidTokenError):
            validate_token(token, secret_key=SECRET, expected_type="access")

    def test_rejects_an_access_token_presented_as_refresh(self) -> None:
        token = create_access_token("1", secret_key=SECRET)
        with pytest.raises(InvalidTokenError):
            validate_token(token, secret_key=SECRET, expected_type="refresh")

    def test_still_raises_token_expired_error_before_checking_type(self) -> None:
        token = create_access_token("1", secret_key=SECRET, expire_minutes=-1)
        with pytest.raises(TokenExpiredError):
            validate_token(token, secret_key=SECRET, expected_type="access")
