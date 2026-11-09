from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from scitracker.domain.publication import Publication
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.storage.repositories import SqlPublicationRepository
from tests.api.helpers import FakeClock, create_user, login

LIST = "/api/v1/reading-list"
PROBLEM = "urn:scitracker:problem:"


def publication(session: Session, number: int = 1) -> int:
    saved = SqlPublicationRepository(session).add(
        Publication(title=f"Paper {number}", authors=[], doi=f"10.1000/api{number}")
    )
    assert saved.id is not None
    return saved.id


def two_users(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> tuple[dict[str, str], dict[str, str]]:
    create_user(session, hasher, "a@example.com")
    create_user(session, hasher, "b@example.com")
    return login(client, "a@example.com"), login(client, "b@example.com")


def add_item(client: TestClient, headers: dict[str, str], pub_id: int) -> int:
    response = client.post(LIST, json={"publication_id": pub_id}, headers=headers)
    assert response.status_code in (200, 201), response.text
    item_id: int = response.json()["id"]
    return item_id


def set_status(client: TestClient, headers: dict[str, str], item_id: int, status: str) -> Any:
    return client.patch(f"{LIST}/{item_id}", json={"status": status}, headers=headers)


def test_every_endpoint_requires_authentication(client: TestClient) -> None:
    assert client.post(LIST, json={"publication_id": 1}).status_code == 401
    assert client.get(LIST).status_code == 401
    assert client.patch(f"{LIST}/1", json={"status": "reading"}).status_code == 401
    assert client.post(f"{LIST}/1/notes", json={"text": "x"}).status_code == 401
    assert client.get(f"{LIST}/1/notes").status_code == 401
    assert client.get(f"{LIST}/1/history").status_code == 401


def test_adding_twice_returns_the_same_item(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    pub = publication(session)
    first = client.post(LIST, json={"publication_id": pub}, headers=headers)
    second = client.post(LIST, json={"publication_id": pub}, headers=headers)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json() == second.json()
    assert first.json()["status"] == "to_read"
    assert first.json()["finished_at"] is None
    assert len(client.get(LIST, headers=headers).json()["items"]) == 1


def test_adding_a_missing_publication_is_a_404_and_a_huge_id_a_422(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    missing = client.post(LIST, json={"publication_id": 999999}, headers=headers)
    assert missing.status_code == 404
    assert missing.json()["type"] == f"{PROBLEM}not-found"
    assert (
        client.post(LIST, json={"publication_id": 99999999999}, headers=headers).status_code == 422
    )


def test_full_path_records_dates_and_history(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher, clock: FakeClock
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    item_id = add_item(client, headers, publication(session))
    clock.advance(days=1)
    assert set_status(client, headers, item_id, "reading").json()["status"] == "reading"
    clock.advance(days=1)
    done = set_status(client, headers, item_id, "done").json()
    assert done["status"] == "done"
    assert done["finished_at"].startswith("2026-11-03T12:00:00")
    history = client.get(f"{LIST}/{item_id}/history", headers=headers).json()
    assert [(h["from_status"], h["to_status"]) for h in history] == [
        ("to_read", "reading"),
        ("reading", "done"),
    ]


def test_skipping_a_status_is_rejected_with_an_explanation(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    item_id = add_item(client, headers, publication(session))
    response = set_status(client, headers, item_id, "done")
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == f"{PROBLEM}invalid-status-transition"
    assert "reading" in body["detail"]
    item = client.get(LIST, headers=headers).json()["items"][0]
    assert (item["status"], item["finished_at"]) == ("to_read", None)
    assert client.get(f"{LIST}/{item_id}/history", headers=headers).json() == []  # nothing written


def test_repeating_done_keeps_the_finish_date_and_adds_no_history(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher, clock: FakeClock
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    item_id = add_item(client, headers, publication(session))
    set_status(client, headers, item_id, "reading")
    first = set_status(client, headers, item_id, "done").json()
    clock.advance(days=30)
    again = set_status(client, headers, item_id, "done")
    assert again.status_code == 200
    assert again.json()["finished_at"] == first["finished_at"]
    assert len(client.get(f"{LIST}/{item_id}/history", headers=headers).json()) == 2


def test_going_back_one_step_is_allowed_and_clears_the_date(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    item_id = add_item(client, headers, publication(session))
    set_status(client, headers, item_id, "reading")
    set_status(client, headers, item_id, "done")
    back = set_status(client, headers, item_id, "reading").json()
    assert (back["status"], back["finished_at"]) == ("reading", None)
    two_steps = set_status(client, headers, item_id, "to_read")
    assert two_steps.status_code == 200  # one step back from "reading" is fine
    set_status(client, headers, item_id, "reading")
    set_status(client, headers, item_id, "done")
    assert set_status(client, headers, item_id, "to_read").status_code == 409


def test_unknown_status_value_is_a_validation_error(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    item_id = add_item(client, headers, publication(session))
    response = set_status(client, headers, item_id, "finished")
    assert response.status_code == 422
    assert response.json()["type"] == f"{PROBLEM}validation-error"


def test_foreign_item_looks_exactly_like_a_missing_one(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    alice, bob = two_users(client, session, hasher)
    item_id = add_item(client, alice, publication(session))
    foreign = set_status(client, bob, item_id, "reading")
    missing = set_status(client, bob, 999999, "reading")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["type"] == missing.json()["type"] == f"{PROBLEM}not-found"
    assert client.get(f"{LIST}/{item_id}/history", headers=bob).status_code == 404
    assert client.get(LIST, headers=bob).json()["items"] == []
    assert client.get(LIST, headers=alice).json()["items"][0]["status"] == "to_read"


def test_notes_are_created_listed_and_validated(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    item_id = add_item(client, headers, publication(session))
    created = client.post(f"{LIST}/{item_id}/notes", json={"text": "  first  "}, headers=headers)
    assert created.status_code == 201
    assert created.json()["text"] == "first"
    client.post(f"{LIST}/{item_id}/notes", json={"text": "second"}, headers=headers)
    texts = [n["text"] for n in client.get(f"{LIST}/{item_id}/notes", headers=headers).json()]
    assert texts == ["first", "second"]
    for bad in ({"text": ""}, {"text": "   "}, {}):
        assert client.post(f"{LIST}/{item_id}/notes", json=bad, headers=headers).status_code == 422


def test_notes_of_another_user_look_nonexistent(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    alice, bob = two_users(client, session, hasher)
    item_id = add_item(client, alice, publication(session))
    client.post(f"{LIST}/{item_id}/notes", json={"text": "private"}, headers=alice)
    read = client.get(f"{LIST}/{item_id}/notes", headers=bob)
    write = client.post(f"{LIST}/{item_id}/notes", json={"text": "intruder"}, headers=bob)
    assert read.status_code == write.status_code == 404
    assert "private" not in read.text
    assert [n["text"] for n in client.get(f"{LIST}/{item_id}/notes", headers=alice).json()] == [
        "private"
    ]


def test_list_filters_by_status_and_paginates_without_duplicates(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    ids = [add_item(client, headers, publication(session, n)) for n in range(5)]
    set_status(client, headers, ids[0], "reading")
    seen: list[int] = []
    cursor: str | None = None
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get(LIST, params=params, headers=headers).json()
        seen += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(ids, reverse=True)
    reading = client.get(LIST, params={"status": "reading"}, headers=headers).json()
    assert [i["id"] for i in reading["items"]] == [ids[0]]
    assert client.get(LIST, params={"status": "nope"}, headers=headers).status_code == 422
