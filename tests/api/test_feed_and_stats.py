from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from scitracker.domain.publication import Author, Publication
from scitracker.domain.topic import Topic
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.storage.repositories import SqlPublicationRepository, SqlTopicRepository
from tests.api.helpers import FakeClock, create_user, login

FEED = "/api/v1/feed"
BY_TOPIC = "/api/v1/stats/by-topic"
TOP_AUTHORS = "/api/v1/stats/top-authors"
READING = "/api/v1/stats/reading"
PROBLEM = "urn:scitracker:problem:"


def make_topic(session: Session, name: str, owner_id: int | None = None) -> int:
    saved = SqlTopicRepository(session).add(Topic(name=name, query="q", owner_id=owner_id))
    assert saved.id is not None
    return saved.id


def make_pub(
    session: Session,
    number: int,
    *,
    published_on: date | None = None,
    authors: tuple[str, ...] = ("Ann Lee",),
    topics: tuple[int, ...] = (),
) -> int:
    repo = SqlPublicationRepository(session)
    saved = repo.add(
        Publication(
            title=f"Paper {number}",
            authors=[Author(name) for name in authors],
            doi=f"10.1000/fs{number}",
            published_on=published_on,
        )
    )
    assert saved.id is not None
    for topic_id in topics:
        repo.link_topic(saved.id, topic_id)
    return saved.id


def ids(response_json: dict) -> list[int]:  # type: ignore[type-arg]
    return [item["id"] for item in response_json["items"]]


def test_all_new_endpoints_require_authentication(client: TestClient) -> None:
    for url in (FEED, BY_TOPIC, f"{TOP_AUTHORS}?topic=1", READING):
        assert client.get(url).status_code == 401, url


def test_feed_shows_public_and_own_topics_but_never_foreign_private_ones(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    alice = create_user(session, hasher, "a@example.com")
    bob = create_user(session, hasher, "b@example.com")
    public = make_topic(session, "Public")
    mine = make_topic(session, "Mine", alice.id)
    theirs = make_topic(session, "Theirs", bob.id)
    in_public = make_pub(session, 1, topics=(public,))
    in_mine = make_pub(session, 2, topics=(mine, public))  # in two topics: shown once
    make_pub(session, 3, topics=(theirs,))
    make_pub(session, 4)  # no topic
    headers = login(client, "a@example.com")
    body = client.get(FEED, headers=headers).json()
    assert ids(body) == [in_mine, in_public]
    narrowed = client.get(FEED, params={"topic": mine}, headers=headers).json()
    assert ids(narrowed) == [in_mine]


def test_foreign_topic_in_the_feed_looks_exactly_like_a_missing_one(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    bob = create_user(session, hasher, "b@example.com")
    theirs = make_topic(session, "Theirs", bob.id)
    headers = login(client, "a@example.com")
    foreign = client.get(FEED, params={"topic": theirs}, headers=headers)
    missing = client.get(FEED, params={"topic": 999999}, headers=headers)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["type"] == f"{PROBLEM}not-found"


def test_feed_pagination_has_no_duplicates_or_gaps(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    alice = create_user(session, hasher, "a@example.com")
    topic = make_topic(session, "Mine", alice.id)
    created = [make_pub(session, n, topics=(topic,)) for n in range(5)]
    headers = login(client, "a@example.com")
    seen: list[int] = []
    cursor: str | None = None
    while True:
        params: dict[str, str | int] = {"topic": topic, "limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = client.get(FEED, params=params, headers=headers).json()
        seen += ids(body)
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(created, reverse=True)


def test_dynamics_fill_empty_months_and_count_per_topic(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    ml, other = make_topic(session, "ML"), make_topic(session, "Other")
    make_pub(session, 1, published_on=date(2026, 1, 10), topics=(ml,))
    make_pub(session, 2, published_on=date(2026, 1, 20), topics=(ml, other))
    make_pub(session, 3, published_on=date(2026, 3, 5), topics=(ml,))
    headers = login(client, "a@example.com")
    params = {"from": "2026-01-01", "to": "2026-03-31"}
    one = client.get(BY_TOPIC, params={**params, "topic": ml}, headers=headers).json()
    assert (one["start"], one["end"]) == ("2026-01-01", "2026-03-31")
    [series] = one["series"]
    assert (series["topic_id"], series["total"]) == (ml, 3)
    assert [(p["month"], p["count"]) for p in series["points"]] == [
        ("2026-01", 2),
        ("2026-02", 0),
        ("2026-03", 1),
    ]
    everything = client.get(BY_TOPIC, params=params, headers=headers).json()
    assert {ml, other} <= {s["topic_id"] for s in everything["series"]}


def test_dynamics_default_to_the_last_twelve_months(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher, clock: FakeClock
) -> None:
    create_user(session, hasher, "a@example.com")
    topic = make_topic(session, "ML")
    body = client.get(
        BY_TOPIC, params={"topic": topic}, headers=login(client, "a@example.com")
    ).json()
    assert (body["start"], body["end"]) == ("2025-12-01", clock().date().isoformat())
    months = [p["month"] for p in body["series"][0]["points"]]
    assert (months[0], months[-1], len(months)) == ("2025-12", "2026-11", 12)


def test_dynamics_hide_foreign_private_topics(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    bob = create_user(session, hasher, "b@example.com")
    theirs = make_topic(session, "Theirs", bob.id)
    headers = login(client, "a@example.com")
    assert theirs not in {
        s["topic_id"] for s in client.get(BY_TOPIC, headers=headers).json()["series"]
    }
    assert client.get(BY_TOPIC, params={"topic": theirs}, headers=headers).status_code == 404


def test_invalid_periods_are_rejected(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    reversed_period = client.get(
        BY_TOPIC, params={"from": "2026-05-01", "to": "2026-04-01"}, headers=headers
    )
    assert reversed_period.status_code == 422
    assert reversed_period.json()["type"] == f"{PROBLEM}invalid-value"
    too_long = client.get(
        BY_TOPIC, params={"from": "2000-01-01", "to": "2026-01-01"}, headers=headers
    )
    assert too_long.status_code == 422
    not_a_date = client.get(BY_TOPIC, params={"from": "yesterday"}, headers=headers)
    assert not_a_date.json()["type"] == f"{PROBLEM}validation-error"
    assert "yesterday" not in not_a_date.text


def test_top_authors(client: TestClient, session: Session, hasher: Argon2PasswordHasher) -> None:
    create_user(session, hasher, "a@example.com")
    bob = create_user(session, hasher, "b@example.com")
    topic = make_topic(session, "ML")
    theirs = make_topic(session, "Theirs", bob.id)
    make_pub(session, 1, authors=("Ann Lee", "Cy Dee"), topics=(topic,))
    make_pub(session, 2, authors=("Ann Lee", "Bob Ray"), topics=(topic,))
    headers = login(client, "a@example.com")
    body = client.get(TOP_AUTHORS, params={"topic": topic, "limit": 2}, headers=headers).json()
    assert body["topic_id"] == topic
    assert [(a["author"], a["publications"]) for a in body["authors"]] == [
        ("Ann Lee", 2),
        ("Bob Ray", 1),
    ]
    assert client.get(TOP_AUTHORS, headers=headers).status_code == 422  # topic is required
    assert client.get(TOP_AUTHORS, params={"topic": theirs}, headers=headers).status_code == 404
    assert (
        client.get(TOP_AUTHORS, params={"topic": topic, "limit": 0}, headers=headers).status_code
        == 422
    )


def test_reading_statistics_follow_my_own_list(
    client: TestClient, session: Session, hasher: Argon2PasswordHasher
) -> None:
    create_user(session, hasher, "a@example.com")
    create_user(session, hasher, "b@example.com")
    alice, bob = login(client, "a@example.com"), login(client, "b@example.com")
    first, second = make_pub(session, 1), make_pub(session, 2)
    item = client.post(
        "/api/v1/reading-list", json={"publication_id": first}, headers=alice
    ).json()["id"]
    client.post("/api/v1/reading-list", json={"publication_id": second}, headers=alice)
    client.patch(f"/api/v1/reading-list/{item}", json={"status": "reading"}, headers=alice)
    client.patch(f"/api/v1/reading-list/{item}", json={"status": "done"}, headers=alice)
    body = client.get(
        READING, params={"from": "2026-11-01", "to": "2026-12-31"}, headers=alice
    ).json()
    assert (body["start"], body["end"]) == ("2026-11-01", "2026-11-01")  # the end is cut to today
    assert (body["added"], body["finished"]) == (2, 1)
    assert body["by_status"] == {"to_read": 1, "reading": 0, "done": 1}
    earlier = client.get(
        READING, params={"from": "2026-10-01", "to": "2026-10-31"}, headers=alice
    ).json()
    assert (earlier["added"], earlier["finished"]) == (0, 0)
    assert earlier["by_status"]["done"] == 1  # the snapshot ignores the period
    nobody = client.get(READING, headers=bob).json()
    assert (nobody["added"], nobody["by_status"]["done"]) == (0, 0)
