from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    """argon2id with the library's recommended parameters (tests pass cheaper ones)."""

    def __init__(self, hasher: Argon2 | None = None) -> None:
        self._hasher = hasher or Argon2()
        self._dummy = self._hasher.hash("timing-equalisation-dummy")

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, password_hash: str | None, password: str) -> bool:
        try:
            self._hasher.verify(password_hash or self._dummy, password)
        except (VerificationError, InvalidHashError):
            return False
        return password_hash is not None
