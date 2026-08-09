"""Unit tests for `querymind.auth.passwords` -- Argon2 hashing, plus verification against both
an Argon2 hash (what `hash_password` actually produces) and a `bcrypt` hash (the "otherwise
bcrypt" migration path -- see the module's own docstring for why both are real, not theoretical).
"""

from __future__ import annotations

import bcrypt
import pytest

from querymind.auth.passwords import hash_password, verify_password


class TestHashPassword:
    def test_returns_an_argon2_formatted_hash(self) -> None:
        assert hash_password("correct horse battery staple").startswith("$argon2")

    def test_never_returns_the_plaintext_password(self) -> None:
        password = "correct horse battery staple"
        assert password not in hash_password(password)

    def test_hashing_the_same_password_twice_produces_different_hashes(self) -> None:
        # Argon2 salts each hash independently, so two hashes of the same password never match
        # byte-for-byte -- both must still verify correctly (see TestVerifyPassword below).
        assert hash_password("same-password") != hash_password("same-password")


class TestVerifyPasswordAgainstArgon2:
    def test_the_correct_password_verifies(self) -> None:
        password_hash = hash_password("s3cr3t-passphrase")
        assert verify_password("s3cr3t-passphrase", password_hash) is True

    def test_the_wrong_password_does_not_verify(self) -> None:
        password_hash = hash_password("s3cr3t-passphrase")
        assert verify_password("wrong-passphrase", password_hash) is False

    def test_an_empty_password_does_not_verify_against_a_real_hash(self) -> None:
        password_hash = hash_password("s3cr3t-passphrase")
        assert verify_password("", password_hash) is False

    def test_a_corrupt_argon2_prefixed_hash_fails_rather_than_raising(self) -> None:
        # Starts with the Argon2 prefix (so it's routed to the Argon2 verifier) but isn't a
        # well-formed PHC string -- must still return False, not raise, per this function's
        # own docstring ("never raises for... a malformed/corrupt hash").
        assert verify_password("anything", "$argon2id$not-a-real-phc-string") is False


class TestVerifyPasswordAgainstBcrypt:
    """A hash produced by `bcrypt` directly -- the "otherwise bcrypt" fallback path this module's
    docstring describes: an existing bcrypt hash from before a hypothetical Argon2 migration
    must still verify correctly, even though `hash_password` itself never produces one.
    """

    @staticmethod
    def _bcrypt_hash(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def test_the_correct_password_verifies(self) -> None:
        password_hash = self._bcrypt_hash("legacy-passphrase")
        assert verify_password("legacy-passphrase", password_hash) is True

    def test_the_wrong_password_does_not_verify(self) -> None:
        password_hash = self._bcrypt_hash("legacy-passphrase")
        assert verify_password("wrong-passphrase", password_hash) is False


class TestVerifyPasswordUnrecognizedFormat:
    def test_raises_value_error_for_a_non_hash_string(self) -> None:
        with pytest.raises(ValueError, match="Unrecognized password hash format"):
            verify_password("anything", "not-a-real-hash-at-all")

    def test_raises_value_error_for_an_empty_hash(self) -> None:
        with pytest.raises(ValueError, match="Unrecognized password hash format"):
            verify_password("anything", "")
