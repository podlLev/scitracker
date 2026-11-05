from argon2 import PasswordHasher

from scitracker.security.passwords import Argon2PasswordHasher

HASHER = Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


def test_correct_password_verifies_and_hash_is_salted() -> None:
    first, second = HASHER.hash_password("secret-phrase-1"), HASHER.hash_password("secret-phrase-1")
    assert first != second
    assert first.startswith("$argon2id$")
    assert HASHER.verify_password(first, "secret-phrase-1")


def test_wrong_password_fails() -> None:
    assert not HASHER.verify_password(HASHER.hash_password("secret-phrase-1"), "other")


def test_unknown_user_never_verifies_even_with_the_dummy_password() -> None:
    assert HASHER.verify_password(None, "anything") is False
    assert HASHER.verify_password(None, "timing-equalisation-dummy") is False


def test_malformed_stored_hash_is_a_failure_not_a_crash() -> None:
    assert HASHER.verify_password("not-a-hash", "x") is False
