import pytest

from scitracker.domain.errors import AuthenticationError, DuplicateRecordError, InvalidValueError
from scitracker.domain.user import Role
from scitracker.services.accounts import (
    authenticate,
    create_admin_user,
    register_user,
)
from tests.services.fakes import FakeHasher, InMemoryUserRepository

PASSWORD = "correct horse battery"


def test_registration_normalizes_email_and_creates_an_ordinary_user() -> None:
    user = register_user(
        InMemoryUserRepository(), FakeHasher(), email="  Ann@Example.com ", password=PASSWORD
    )
    assert (user.email, user.role) == ("ann@example.com", Role.USER)
    assert user.password_hash == f"hashed:{PASSWORD}"


def test_admin_creation_sets_the_role() -> None:
    admin = create_admin_user(
        InMemoryUserRepository(), FakeHasher(), email="a@example.com", password=PASSWORD
    )
    assert admin.role is Role.ADMIN


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_password_length_is_enforced(password: str) -> None:
    users, hasher = InMemoryUserRepository(), FakeHasher()
    with pytest.raises(InvalidValueError, match="password"):
        register_user(users, hasher, email="a@example.com", password=password)


def test_invalid_email_is_rejected_before_the_costly_hashing() -> None:
    hasher = FakeHasher()
    with pytest.raises(InvalidValueError):
        register_user(InMemoryUserRepository(), hasher, email="nope", password=PASSWORD)
    assert hasher.hashed == 0


def test_duplicate_email_is_rejected() -> None:
    users = InMemoryUserRepository()
    register_user(users, FakeHasher(), email="a@example.com", password=PASSWORD)
    with pytest.raises(DuplicateRecordError):
        register_user(users, FakeHasher(), email="A@example.com", password=PASSWORD)


def test_authentication_succeeds_with_the_right_password() -> None:
    users, hasher = InMemoryUserRepository(), FakeHasher()
    register_user(users, hasher, email="a@example.com", password=PASSWORD)
    assert authenticate(users, hasher, email=" A@Example.com", password=PASSWORD).id == 1


def test_wrong_password_is_rejected() -> None:
    users, hasher = InMemoryUserRepository(), FakeHasher()
    register_user(users, hasher, email="a@example.com", password=PASSWORD)
    with pytest.raises(AuthenticationError):
        authenticate(users, hasher, email="a@example.com", password="another password")


def test_unknown_email_still_runs_a_verification() -> None:
    hasher = FakeHasher()
    with pytest.raises(AuthenticationError):
        authenticate(InMemoryUserRepository(), hasher, email="x@example.com", password=PASSWORD)
    assert hasher.verified_with == [None]  # same work as for a known user
