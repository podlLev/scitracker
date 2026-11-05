from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from scitracker.domain.publication import Author, Publication
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
from scitracker.storage.repositories import (
    SqlPublicationRepository,
    SqlTopicRepository,
    SqlUserRepository,
)

URL = "/api/v1/publications"
PROBLEM = "urn:scitracker:problem:"


def add(
    session: Session,
    number: int,
    *,
    title: str | None = None,
    authors: tuple[str, ...] = ("Ann Lee",),
    published_on: date | None = None,
) -> int:
    saved = SqlPublicationRepository(session).add(
        Publication(
            title=title or f"Paper {number}",
            authors=[Author(name) for name in authors],
            doi=f"10.1000/t{number}",
            published_on=published_on,
        )
    )
    assert saved.id is not None
    return saved.id


def ids(response: Any) -> list[int]:
    return [item["id"] for item in response.json()["items"]]


def titles(response: Any) -> list[str]:
    return [item["title"] for item in response.json()["items"]]


def walk(client: TestClient, **params: object) -> list[list[int]]:
    pages: list[list[int]] = []
    cursor: str | None = None
    while True:
        query = {**params, "cursor": cursor} if cursor else dict(params)
        body = client.get(URL, params=query).json()  # type: ignore[arg-type]
        pages.append([item["id"] for item in body["items"]])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages


def test_empty_database_gives_an_empty_page(client: TestClient) -> None:
    assert client.get(URL).json() == {"items": [], "next_cursor": None}


def test_items_have_expected_fields_and_newest_comes_first(
    client: TestClient, session: Session
) -> None:
    first = add(session, 1, authors=("Ann Lee", "Bob Ray"), published_on=date(2024, 5, 1))
    second = add(session, 2)
    body = client.get(URL).json()
    assert [item["id"] for item in body["items"]] == [second, first]
    older = body["items"][1]
    assert older["authors"] == ["Ann Lee", "Bob Ray"]
    assert older["doi"] == "10.1000/t1"
    assert older["published_on"] == "2024-05-01"


def test_title_search_ignores_case_and_escapes_wildcards(
    client: TestClient, session: Session
) -> None:
    add(session, 1, title="Graph Neural Networks")
    add(session, 2, title="100% sure")
    add(session, 3, title="Something else")
    assert titles(client.get(URL, params={"q": "NEURAL"})) == ["Graph Neural Networks"]
    assert titles(client.get(URL, params={"q": "100%"})) == ["100% sure"]
    assert titles(client.get(URL, params={"q": "_"})) == []


def test_filter_by_author(client: TestClient, session: Session) -> None:
    wanted = add(session, 1, authors=("Ann Lee",))
    add(session, 2, authors=("Bob Ray",))
    assert ids(client.get(URL, params={"author": "ann"})) == [wanted]


def test_filter_by_topic(client: TestClient, session: Session) -> None:
    topic = SqlTopicRepository(session).add(Topic(name="ML", query="ml"))
    assert topic.id is not None
    inside = add(session, 1)
    add(session, 2)
    SqlPublicationRepository(session).link_topic(inside, topic.id)
    assert ids(client.get(URL, params={"topic": topic.id})) == [inside]


def test_filter_by_publication_date(client: TestClient, session: Session) -> None:
    add(session, 1, published_on=date(2020, 1, 1))
    recent = add(session, 2, published_on=date(2024, 6, 1))
    add(session, 3, published_on=None)
    assert ids(client.get(URL, params={"from": "2024-01-01"})) == [recent]


def test_pagination_visits_every_record_exactly_once(client: TestClient, session: Session) -> None:
    created = [add(session, n) for n in range(25)]
    pages = walk(client, limit=10)
    assert [len(page) for page in pages] == [10, 10, 5]
    assert [i for page in pages for i in page] == sorted(created, reverse=True)


def test_pagination_stays_stable_when_new_records_arrive(
    client: TestClient, session: Session
) -> None:
    old = [add(session, n) for n in range(15)]
    first = client.get(URL, params={"limit": 10}).json()
    add(session, 100)  # new records arrive between the two requests
    add(session, 101)
    second = client.get(URL, params={"limit": 10, "cursor": first["next_cursor"]}).json()
    seen = [i["id"] for i in first["items"]] + [i["id"] for i in second["items"]]
    assert seen == sorted(old, reverse=True)  # no duplicates, nothing skipped
    assert second["next_cursor"] is None


def test_get_publication(client: TestClient, session: Session) -> None:
    pub_id = add(session, 1, title="Single")
    response = client.get(f"{URL}/{pub_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Single"


def test_unknown_publication_is_a_404_problem(client: TestClient) -> None:
    response = client.get(f"{URL}/999999")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == f"{PROBLEM}not-found"


def test_id_beyond_database_range_is_a_422_not_a_500(client: TestClient) -> None:
    assert client.get(f"{URL}/99999999999").status_code == 422


def test_invalid_cursor_is_a_problem(client: TestClient) -> None:
    response = client.get(URL, params={"cursor": "garbage"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == f"{PROBLEM}invalid-cursor"


def test_validation_errors_name_fields_and_do_not_echo_input(client: TestClient) -> None:
    response = client.get(URL, params={"limit": "0", "from": "not-a-date"})
    body = response.json()
    assert response.status_code == 422
    assert body["type"] == f"{PROBLEM}validation-error"
    assert {error["field"] for error in body["errors"]} == {"query.limit", "query.from"}
    assert "not-a-date" not in response.text


def test_topics_endpoint_lists_only_public_topics(client: TestClient, session: Session) -> None:
    owner = SqlUserRepository(session).add(User(email="o@example.com", password_hash="x"))
    repo = SqlTopicRepository(session)
    repo.add(Topic(name="Public", query="p"))
    repo.add(Topic(name="Private", query="q", owner_id=owner.id))
    response = client.get("/api/v1/topics")
    assert [t["name"] for t in response.json()] == ["Public"]
    assert response.json()[0]["public"] is True


def test_healthz_is_ok(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
