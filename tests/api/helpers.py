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
