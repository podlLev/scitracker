from dataclasses import replace

from scitracker.domain.errors import AuthenticationError, InvalidValueError
from scitracker.domain.user import Role, User
from scitracker.services.ports import PasswordHasher, UserRepository

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128  # also bounds the work an attacker can force on the hasher


def _create(
    users: UserRepository, hasher: PasswordHasher, email: str, password: str, role: Role
) -> User:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidValueError(
            f"password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters long"
        )
    unset = "unset"
    candidate = User(email=email, password_hash=unset, role=role)  # validates before hashing
    return users.add(replace(candidate, password_hash=hasher.hash_password(password)))


def register_user(
    users: UserRepository, hasher: PasswordHasher, *, email: str, password: str
) -> User:
    """Self-registration always creates an ordinary user."""
    return _create(users, hasher, email, password, Role.USER)


def create_admin_user(
    users: UserRepository, hasher: PasswordHasher, *, email: str, password: str
) -> User:
    """Not reachable from the API: used by the create_admin script only."""
    return _create(users, hasher, email, password, Role.ADMIN)


def authenticate(
    users: UserRepository, hasher: PasswordHasher, *, email: str, password: str
) -> User:
    user = users.get_by_email(email.strip().lower())
    password_ok = hasher.verify_password(user.password_hash if user else None, password)
    if user is None or not password_ok:
        raise AuthenticationError("Invalid email or password.")
    return user
