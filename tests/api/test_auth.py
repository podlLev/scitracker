from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.security.tokens import JwtTokenService
from tests.api.helpers import PASSWORD, TEST_SECRET, create_user, login

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/me"
PROBLEM = "urn:scitracker:problem:"


def test_register_creates_a_user_and_never_returns_secrets(client: TestClient) -> None:
    response = client.post(REGISTER, json={"email": "Ann@Example.com", "password": PASSWORD})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "role"}
    assert (body["email"], body["role"]) == ("ann@example.com", "user")


def test_role_cannot_be_chosen_by_the_client(client: TestClient) -> None:
    response = client.post(
        REGISTER, json={"email": "a@example.com", "password": PASSWORD, "role": "admin"}
    )
    assert response.json()["role"] == "user"


def test_duplicate_email_is_a_conflict(client: TestClient) -> None:
    payload = {"email": "a@example.com", "password": PASSWORD}
    client.post(REGISTER, json=payload)
    second = client.post(REGISTER, json={**payload, "email": "A@example.com"})
    assert second.status_code == 409
    assert second.json()["type"] == f"{PROBLEM}duplicate-record"


def test_weak_password_is_rejected_without_echoing_it(client: TestClient) -> None:
    response = client.post(REGISTER, json={"email": "a@example.com", "password": "pw-xyz9"})
    assert response.status_code == 422
    assert "pw-xyz9" not in response.text
    assert response.json()["errors"][0]["field"] == "body.password"


def test_invalid_email_is_rejected(client: TestClient) -> None:
    response = client.post(REGISTER, json={"email": "not-an-email", "password": PASSWORD})
    assert response.status_code == 422


def test_login_returns_a_working_token(client: TestClient) -> None:
    client.post(REGISTER, json={"email": "a@example.com", "password": PASSWORD})
    response = client.post(LOGIN, json={"email": "A@Example.com", "password": PASSWORD})
    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1800
    me = client.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == "a@example.com"


def test_wrong_password_and_unknown_email_look_identical(client: TestClient) -> None:
    client.post(REGISTER, json={"email": "a@example.com", "password": PASSWORD})
    wrong = client.post(LOGIN, json={"email": "a@example.com", "password": "wrong-password-1"})
    unknown = client.post(LOGIN, json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["type"] == f"{PROBLEM}authentication-failed"
    assert wrong.headers["www-authenticate"] == "Bearer"


def test_protected_endpoint_requires_a_valid_token(client: TestClient) -> None:
    assert client.get(ME).status_code == 401
    assert client.get(ME, headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get(ME, headers={"Authorization": "Basic abc"}).status_code == 401


def test_expired_token_is_rejected(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    user = create_user(session, hasher, "a@example.com")
    assert user.id is not None
    stale = JwtTokenService(
        TEST_SECRET, ttl=timedelta(minutes=1), clock=lambda: datetime(2020, 1, 1, tzinfo=UTC)
    ).issue(user.id)
    assert client.get(ME, headers={"Authorization": f"Bearer {stale}"}).status_code == 401


def test_token_of_a_deleted_user_stops_working(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "gone@example.com")
    headers = login(client, "gone@example.com")
    session.execute(text("DELETE FROM users WHERE email = 'gone@example.com'"))
    assert client.get(ME, headers=headers).status_code == 401


def test_guests_can_still_search(client: TestClient) -> None:
    assert client.get("/api/v1/publications").status_code == 200
