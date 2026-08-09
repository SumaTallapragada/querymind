"""Password hashing -- Argon2 (preferred) for new hashes, with `bcrypt` verification kept
available for any hash that was produced by it.

Argon2 (via `argon2-cffi`, the reference `PasswordHasher`) is what `hash_password` always uses
-- it is the current OWASP-recommended KDF for password storage and is a committed project
dependency, so there is no "Argon2 unavailable" runtime branch to fall back from here. `bcrypt`
is included as a second, real dependency (not theoretical) specifically so `verify_password`
can correctly check a hash produced by either scheme: a hash-scheme upgrade (bcrypt -> Argon2)
must never invalidate passwords hashed before the upgrade, and that migration path is exactly
what "otherwise bcrypt" means here -- an existing hash's own prefix says which algorithm
produced it, not a global, one-time choice.

Every function only ever handles a password as a Python `str`/hash `str` -- callers never see a
raw `bytes` digest or a library-specific hash object.
"""

from __future__ import annotations

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_ARGON2_PREFIX = "$argon2"
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash `password` with Argon2id, returning a self-describing PHC-format string (the
    algorithm, its parameters, and the salt are all encoded in the returned string itself --
    `verify_password` needs nothing else to check a password against it later).
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether `password` matches `password_hash`, whichever scheme produced it.

    Never raises for a wrong password (or a malformed/corrupt hash) -- only for a `password_hash`
    that isn't recognizable as either scheme's output at all, which signals a programming error
    (a non-hash string reached this function), not a legitimate "wrong password" outcome.
    """
    if password_hash.startswith(_ARGON2_PREFIX):
        try:
            return _hasher.verify(password_hash, password)
        except VerificationError:
            # Covers both a genuine wrong-password mismatch (`VerifyMismatchError`, a
            # `VerificationError` subclass) and a malformed/corrupt PHC string that fails to
            # even parse (a plain `VerificationError`, e.g. "Decoding failed") -- argon2-cffi's
            # own `InvalidHashError`/`InvalidHash` are unrelated `ValueError` subclasses raised
            # by different APIs, never by `PasswordHasher.verify` itself.
            return False

    if password_hash.startswith(_BCRYPT_PREFIXES):
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    raise ValueError(f"Unrecognized password hash format: {password_hash[:10]!r}...")
