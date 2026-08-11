"""API-key generation and hashing -- pure functions, mirrors `querymind.auth.passwords`'s shape
exactly, applied to a different secret type.

An API key is 256 bits of `secrets`-module randomness, never user-chosen (unlike a password),
so a fast digest (SHA-256) is the right tool here, not Argon2/bcrypt: there is no low-entropy
guessing surface a slow KDF would need to defend against, only brute-forcing 2**256 possible
values, which no hash speed makes feasible. Every function only ever handles the raw key and its
hash as `str` -- callers never see raw bytes.

The `qm_` prefix is a plaintext, non-secret label kept for at-a-glance identification in logs,
support tickets, and the key-management UI (`qm_Ab3f...`) -- revealing it (or the few characters
`api_key_prefix` keeps for display) does not meaningfully weaken a 256-bit secret.
"""

from __future__ import annotations

import hashlib
import secrets

API_KEY_PREFIX = "qm_"

#: `secrets.token_urlsafe(32)` yields 256 bits of entropy, ~43 base64url characters.
_TOKEN_BYTES = 32

#: `qm_` (3 chars) + 8 characters of the random token -- enough for a human to visually
#: distinguish keys in a list, not enough to matter for an attacker guessing the other ~250 bits.
_DISPLAY_PREFIX_LENGTH = len(API_KEY_PREFIX) + 8


def generate_raw_api_key() -> str:
    """Generate a fresh, cryptographically random API key: `qm_` + 256 bits of randomness.

    Returned exactly once to the caller that created it -- see
    `AuthenticationService.create_api_key`'s own docstring for why nothing above this function
    ever persists the return value itself, only its hash.
    """
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(_TOKEN_BYTES)}"


def hash_api_key(raw_key: str) -> str:
    """Return the SHA-256 hex digest of `raw_key` -- the only form of an API key ever persisted."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def api_key_prefix(raw_key: str) -> str:
    """Return the short, non-secret, human-identifiable prefix of `raw_key`, stored in plaintext
    alongside its hash so a key-management UI can show "which key is this" without ever
    reconstructing or storing the full secret.
    """
    return raw_key[:_DISPLAY_PREFIX_LENGTH]
