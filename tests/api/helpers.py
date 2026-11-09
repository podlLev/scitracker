from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from scitracker.domain.user import Role, User
from scitracker.services.ports import PasswordHasher
from scitracker.storage.repositories import SqlUserRepository

TEST_SECRET = "test-secret-" + "x" * 40
PASSWORD = "correct horse battery"


def create_user(
    session: Session, hasher: PasswordHasher, email: str, *, role: Role = Role.USER
) -> User:
    return SqlUserRepository(session).add(
        User(email=email, password_hash=hasher.hash_password(PASSWORD), role=role)
    )


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class FakeClock:
    """The API's notion of 'now', controlled by the test."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 1, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)
