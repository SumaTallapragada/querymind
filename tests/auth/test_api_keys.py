"""Unit tests for `querymind.auth.api_keys` -- pure functions, no database, mirrors
`tests/auth/test_passwords.py`'s shape for the same kind of module.
"""

from __future__ import annotations

from querymind.auth.api_keys import (
    API_KEY_PREFIX,
    api_key_prefix,
    generate_raw_api_key,
    hash_api_key,
)


class TestGenerateRawApiKey:
    def test_starts_with_the_qm_prefix(self) -> None:
        assert generate_raw_api_key().startswith(API_KEY_PREFIX)

    def test_two_calls_never_produce_the_same_key(self) -> None:
        assert generate_raw_api_key() != generate_raw_api_key()

    def test_carries_meaningful_entropy(self) -> None:
        """Not a strict entropy measurement -- just a floor against an accidental regression to
        a short/predictable value (e.g. a bug that truncates `secrets.token_urlsafe`'s output).
        """
        raw_key = generate_raw_api_key()
        assert len(raw_key) >= 40


class TestHashApiKey:
    def test_is_deterministic(self) -> None:
        raw_key = generate_raw_api_key()
        assert hash_api_key(raw_key) == hash_api_key(raw_key)

    def test_different_keys_hash_differently(self) -> None:
        assert hash_api_key(generate_raw_api_key()) != hash_api_key(generate_raw_api_key())

    def test_is_a_64_character_hex_sha256_digest(self) -> None:
        digest = hash_api_key(generate_raw_api_key())
        assert len(digest) == 64
        assert all(char in "0123456789abcdef" for char in digest)

    def test_never_equals_or_contains_the_raw_key(self) -> None:
        raw_key = generate_raw_api_key()
        digest = hash_api_key(raw_key)
        assert digest != raw_key
        assert raw_key not in digest


class TestApiKeyPrefix:
    def test_is_a_prefix_of_the_raw_key(self) -> None:
        raw_key = generate_raw_api_key()
        assert raw_key.startswith(api_key_prefix(raw_key))

    def test_starts_with_qm(self) -> None:
        assert api_key_prefix(generate_raw_api_key()).startswith(API_KEY_PREFIX)

    def test_is_much_shorter_than_the_full_key(self) -> None:
        raw_key = generate_raw_api_key()
        assert len(api_key_prefix(raw_key)) < len(raw_key)
