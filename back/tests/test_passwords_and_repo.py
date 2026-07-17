"""Tests for password hashing and repository primitives."""

from __future__ import annotations

from app.models import User
from app.repositories import QuerySpec, user_repository
from app.security.passwords import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    hashed = hash_password("s3cret!", rounds=4)
    assert hashed.startswith("$2b$")
    assert verify_password("s3cret!", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_verify_handles_garbage_gracefully():
    assert verify_password("x", "") is False
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_repository_add_find_count_page(app):
    with app.app_context():
        # Seed with unique-to-this-test usernames so we don't collide with
        # rows left by other tests (pytest session-scoped sqlite in-memory).
        baseline = user_repository.count()
        prefix = "repo_test_"
        for i in range(5):
            user_repository.add(
                User(
                    username=f"{prefix}{i}",
                    password=hash_password("pw", rounds=4),
                    enabled=True,
                )
            )

        assert user_repository.username_exists(f"{prefix}1") is True
        assert user_repository.username_exists("nope") is False
        assert user_repository.count() == baseline + 5

        spec = QuerySpec(
            filters=[User.username.like(f"{prefix}%")],
            order_by=[User.username.asc()],
            page=0,
            size=2,
        )
        p1 = user_repository.page(spec)
        assert p1.total == 5
        assert len(p1.items) == 2
        assert p1.items[0].username == f"{prefix}0"

        spec2 = QuerySpec(
            filters=[User.username.like(f"{prefix}%")],
            order_by=[User.username.asc()],
            page=1,
            size=2,
        )
        p2 = user_repository.page(spec2)
        assert p2.total == 5
        assert [u.username for u in p2.items] == [f"{prefix}2", f"{prefix}3"]
