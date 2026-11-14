from typing import TYPE_CHECKING, Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from scitracker.cache.memory import InMemoryTtlCache, NullCache
from scitracker.domain.user import Role
from scitracker.services.cache import Cache
from scitracker.services.ports import PasswordHasher
from tests.api.helpers import FakeClock, create_user, login

if TYPE_CHECKING:
    from fastapi import FastAPI

BY_TOPIC = "/api/v1/stats/by-topic"
TOP_AUTHORS = "/api/v1/stats/top-authors"
TOPICS = "/api/v1/topics"


def _use_cache(client: TestClient, cache: Cache | None) -> None:
    cast("FastAPI", client.app).state.cache = cache


def _fresh(client: TestClient) -> InMemoryTtlCache:
    cache = InMemoryTtlCache(ttl_seconds=60)
    _use_cache(client, cache)
    return cache


def _xcache(response: Any) -> str | None:
    value = response.headers.get("x-cache")
    return None if value is None else str(value)


def _names(response: Any) -> set[str]:
    return {item["topic"] for item in response.json()["series"]}


def _make_topic(
    client: TestClient, headers: dict[str, str], name: str, *, public: bool = False
) -> int:
    response = client.post(
        TOPICS,
        json={"name": name, "query": f"{name} query", "public": public},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_by_topic_is_cached(client: TestClient, session: Session, hasher: PasswordHasher) -> None:
    _fresh(client)
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    first = client.get(BY_TOPIC, headers=headers)
    second = client.get(BY_TOPIC, headers=headers)
    assert first.status_code == second.status_code == 200
    assert (_xcache(first), _xcache(second)) == ("MISS", "HIT")
    assert first.json() == second.json()


def test_private_topic_is_not_leaked_between_users(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    _fresh(client)
    create_user(session, hasher, "a@example.com")
    create_user(session, hasher, "b@example.com")
    alice = login(client, "a@example.com")
    bob = login(client, "b@example.com")
    _make_topic(client, alice, "Alice private topic")

    mine = client.get(BY_TOPIC, headers=alice)
    mine_again = client.get(BY_TOPIC, headers=alice)
    theirs = client.get(BY_TOPIC, headers=bob)

    assert "Alice private topic" in _names(mine)
    assert _xcache(mine_again) == "HIT"
    assert _xcache(theirs) == "MISS"  # Bob must not be served Alice's entry
    assert "Alice private topic" not in _names(theirs)


def test_top_authors_cache_does_not_bypass_ownership(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    _fresh(client)
    create_user(session, hasher, "a@example.com")
    create_user(session, hasher, "b@example.com")
    alice = login(client, "a@example.com")
    bob = login(client, "b@example.com")
    topic_id = _make_topic(client, alice, "Alice authors topic")

    first = client.get(TOP_AUTHORS, params={"topic": topic_id}, headers=alice)
    second = client.get(TOP_AUTHORS, params={"topic": topic_id}, headers=alice)
    foreign = client.get(TOP_AUTHORS, params={"topic": topic_id}, headers=bob)

    assert (first.status_code, _xcache(first)) == (200, "MISS")
    assert _xcache(second) == "HIT"
    assert foreign.status_code == 404
    assert _xcache(foreign) is None


def test_creating_a_topic_invalidates_stats(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    _fresh(client)
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    client.get(BY_TOPIC, headers=headers)
    assert _xcache(client.get(BY_TOPIC, headers=headers)) == "HIT"

    _make_topic(client, headers, "Freshly created topic")
    after = client.get(BY_TOPIC, headers=headers)
    assert _xcache(after) == "MISS"
    assert "Freshly created topic" in _names(after)


def test_deleting_a_topic_invalidates_stats(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    _fresh(client)
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    topic_id = _make_topic(client, headers, "Doomed topic")
    assert "Doomed topic" in _names(client.get(BY_TOPIC, headers=headers))

    assert client.delete(f"{TOPICS}/{topic_id}", headers=headers).status_code == 204
    after = client.get(BY_TOPIC, headers=headers)
    assert _xcache(after) == "MISS"
    assert "Doomed topic" not in _names(after)


def test_public_topics_are_cached_and_invalidated(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    _fresh(client)
    create_user(session, hasher, "admin@example.com", role=Role.ADMIN)
    admin = login(client, "admin@example.com")

    first = client.get(TOPICS)
    second = client.get(TOPICS)
    assert (_xcache(first), _xcache(second)) == ("MISS", "HIT")

    _make_topic(client, admin, "Brand new public topic", public=True)
    after = client.get(TOPICS)
    assert _xcache(after) == "MISS"
    assert "Brand new public topic" in {item["name"] for item in after.json()}


def test_new_day_uses_a_new_key(
    client: TestClient, session: Session, hasher: PasswordHasher, clock: FakeClock
) -> None:
    _fresh(client)
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    client.get(BY_TOPIC, headers=headers)
    assert _xcache(client.get(BY_TOPIC, headers=headers)) == "HIT"
    clock.advance(days=1)
    assert _xcache(client.get(BY_TOPIC, headers=headers)) == "MISS"


def test_different_parameters_are_cached_separately(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    _fresh(client)
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    topic_id = _make_topic(client, headers, "Parameter topic")
    assert _xcache(client.get(BY_TOPIC, headers=headers)) == "MISS"
    params = {"topic": topic_id}
    assert _xcache(client.get(BY_TOPIC, params=params, headers=headers)) == "MISS"
    assert _xcache(client.get(BY_TOPIC, headers=headers)) == "HIT"
    assert _xcache(client.get(BY_TOPIC, params=params, headers=headers)) == "HIT"


def test_errors_are_not_cached(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    cache = _fresh(client)
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    missing = client.get(BY_TOPIC, params={"topic": 999_999}, headers=headers)
    reversed_period = client.get(
        BY_TOPIC, params={"from": "2026-02-01", "to": "2026-01-01"}, headers=headers
    )
    assert missing.status_code == 404
    assert reversed_period.status_code == 422
    assert _xcache(missing) is None
    assert _xcache(reversed_period) is None
    assert cache.size() == 0


def test_personal_endpoints_are_never_cached(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    cache = _fresh(client)
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    reading = client.get("/api/v1/stats/reading", headers=headers)
    reading_list = client.get("/api/v1/reading-list", headers=headers)
    assert reading.status_code == 200
    assert _xcache(reading) is None
    assert _xcache(reading_list) is None
    assert cache.size() == 0


def test_disabled_cache_never_hits(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    _use_cache(client, NullCache())
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    results = [_xcache(client.get(BY_TOPIC, headers=headers)) for _ in range(3)]
    assert results == ["MISS", "MISS", "MISS"]


def test_missing_cache_falls_back_to_computing(
    client: TestClient, session: Session, hasher: PasswordHasher
) -> None:
    _use_cache(client, None)
    create_user(session, hasher, "a@example.com")
    headers = login(client, "a@example.com")
    response = client.get(BY_TOPIC, headers=headers)
    assert (response.status_code, _xcache(response)) == (200, "MISS")
