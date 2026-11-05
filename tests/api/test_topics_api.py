from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from scitracker.domain.topic import Topic
from scitracker.domain.user import Role
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.services.topics import MAX_PRIVATE_TOPICS
from scitracker.storage.repositories import SqlTopicRepository
from tests.api.helpers import create_user, login

TOPICS = "/api/v1/topics"
PROBLEM = "urn:scitracker:problem:"


def two_users(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> tuple[dict[str, str], dict[str, str]]:
    create_user(session, hasher, "a@example.com")
    create_user(session, hasher, "b@example.com")
    return login(client, "a@example.com"), login(client, "b@example.com")


def test_creating_a_topic_requires_authentication(client: TestClient) -> None:
    assert client.post(TOPICS, json={"name": "ML", "query": "ml"}).status_code == 401
    assert client.delete(f"{TOPICS}/1").status_code == 401


def test_private_topics_are_visible_only_to_their_owner(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    alice, bob = two_users(client, session, hasher)
    created = client.post(TOPICS, json={"name": "Mine", "query": "q"}, headers=alice)
    assert created.status_code == 201
    assert created.json()["public"] is False
    mine = client.get("/api/v1/me/topics", headers=alice).json()
    assert [t["name"] for t in mine] == ["Mine"]
    assert client.get("/api/v1/me/topics", headers=bob).json() == []
    assert client.get(TOPICS).json() == []  # not in the public list


def test_foreign_private_topic_looks_nonexistent(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    alice, bob = two_users(client, session, hasher)
    topic_id = client.post(TOPICS, json={"name": "Mine", "query": "q"}, headers=alice).json()["id"]
    foreign = client.delete(f"{TOPICS}/{topic_id}", headers=bob)
    missing = client.delete(f"{TOPICS}/999999", headers=bob)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["type"] == f"{PROBLEM}not-found"
    assert client.delete(f"{TOPICS}/{topic_id}", headers=alice).status_code == 204


def test_ordinary_user_cannot_manage_public_topics(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    alice, _ = two_users(client, session, hasher)
    denied = client.post(TOPICS, json={"name": "P", "query": "p", "public": True}, headers=alice)
    assert denied.status_code == 403
    assert denied.json()["type"] == f"{PROBLEM}forbidden"
    public = SqlTopicRepository(session).add(Topic(name="Public", query="p"))
    assert client.delete(f"{TOPICS}/{public.id}", headers=alice).status_code == 403


def test_administrator_manages_public_topics(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "admin@example.com", role=Role.ADMIN)
    admin = login(client, "admin@example.com")
    created = client.post(TOPICS, json={"name": "P", "query": "p", "public": True}, headers=admin)
    assert created.status_code == 201
    assert created.json()["public"] is True
    assert [t["name"] for t in client.get(TOPICS).json()] == ["P"]  # visible to guests
    deleted = client.delete(f"{TOPICS}/{created.json()['id']}", headers=admin)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(TOPICS).json() == []


def test_administrator_cannot_see_foreign_private_topics(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "admin@example.com", role=Role.ADMIN)
    alice, _ = two_users(client, session, hasher)
    topic_id = client.post(TOPICS, json={"name": "Mine", "query": "q"}, headers=alice).json()["id"]
    admin = login(client, "admin@example.com")
    assert client.delete(f"{TOPICS}/{topic_id}", headers=admin).status_code == 404


def test_private_topic_quota(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    user = create_user(session, hasher, "a@example.com")
    repo = SqlTopicRepository(session)
    for n in range(MAX_PRIVATE_TOPICS):
        repo.add(Topic(name=f"T{n}", query="q", owner_id=user.id))
    response = client.post(
        TOPICS, json={"name": "One more", "query": "q"}, headers=login(client, "a@example.com")
    )
    assert response.status_code == 409
    assert response.json()["type"] == f"{PROBLEM}quota-exceeded"


def test_blank_topic_fields_are_rejected(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    response = client.post(TOPICS, json={"name": "  ", "query": "q"}, headers=headers)
    assert response.status_code == 422
