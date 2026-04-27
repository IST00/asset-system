"""Password hashing — direct bcrypt, no passlib.

Why
---
passlib 1.7.x imports the stdlib `crypt` module at top level, which is
deprecated in Python 3.13 and will be removed in 3.14. Rather than pin an
unmaintained compatibility shim, we call `bcrypt` directly; the API surface
we need is tiny.

Contract
--------
- `hash_password(raw)` returns a str safe for DB storage.
- `verify_password(raw, stored)` returns bool. Never raises on garbage input.
- Rounds default to 12 (bcrypt safe range: 10–14). Override via env
  `BCRYPT_ROUNDS` for benchmarks/tests; tests run at rounds=4 to stay fast.

Compatibility
-------------
The original seed hash in `migrations/versions/001_init.py` is a standard
`$2b$10$…` bcrypt string. bcrypt.checkpw parses the cost transparently,
so legacy hashes remain verifiable.
"""

from __future__ import annotations

import os

import bcrypt

_DEFAULT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))


def hash_password(raw: str, *, rounds: int | None = None) -> str:
    cost = rounds if rounds is not None else _DEFAULT_ROUNDS
    salt = bcrypt.gensalt(rounds=cost)
    hashed = bcrypt.hashpw(raw.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(raw: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), stored.encode("utf-8"))
    except (ValueError, TypeError):
        return False


__all__ = ["hash_password", "verify_password"]
