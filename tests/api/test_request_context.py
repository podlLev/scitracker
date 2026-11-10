import logging
import re
from collections.abc import Callable

from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scitracker.api.app import create_app
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.security.tokens import JwtTokenService
from tests.api.helpers import PASSWORD, TEST_SECRET
from tests.conftest import CapturedLogs


def ok() -> None:
    return None


def unused_scope():  # type: ignore[no-untyped-def]
    raise AssertionError("these tests never open a database scope")


def make_app(ping: Callable[[], None] = ok) -> FastAPI:
    return create_app(
        scope=unused_scope,
        ping=ping,
        hasher=Argon2PasswordHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)),
        tokens=JwtTokenService(TEST_SECRET),
    )


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    first = client.get("/healthz")
    second = client.get("/healthz")
    assert re.fullmatch(r"[0-9a-f]{32}", first.headers["x-request-id"])
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_error_responses_carry_it_too(client: TestClient) -> None:
    assert client.get("/nope").headers["x-request-id"]  # 404
    assert client.get("/api/v1/publications", params={"limit": 0}).headers["x-request-id"]  # 422
    assert client.get("/api/v1/me").headers["x-request-id"]  # 401


def test_a_sane_client_id_is_echoed_and_a_bad_one_replaced(client: TestClient) -> None:
    good = client.get("/healthz", headers={"X-Request-ID": "trace-0123456789"})
    assert good.headers["x-request-id"] == "trace-0123456789"
    for bad in ("short", "has space in it!", "x" * 65, "bad;id=1,2,3"):
        replaced = client.get("/healthz", headers={"X-Request-ID": bad}).headers["x-request-id"]
        assert replaced != bad
        assert re.fullmatch(r"[0-9a-f]{32}", replaced)


def test_every_log_line_of_a_request_shares_its_id(json_logs: CapturedLogs) -> None:
    app = make_app()

    @app.get("/probe")
    def probe() -> dict[str, str]:  # a sync handler runs in a worker thread
        logging.getLogger("scitracker.probe").info("inside the handler")
        return {"ok": "yes"}

    client = TestClient(app)
    client.get("/probe", headers={"X-Request-ID": "trace-0123456789"})
    logging.getLogger("scitracker.probe").info("after the request")
    records = {r["message"]: r for r in json_logs.records()}
    assert records["inside the handler"]["request_id"] == "trace-0123456789"
    access = records["GET /probe 200"]
    assert access["request_id"] == "trace-0123456789"
    assert (access["method"], access["path"], access["status"]) == ("GET", "/probe", 200)
    assert access["route"] == "/probe"
    assert access["duration_ms"] >= 0
    assert "request_id" not in records["after the request"]


def test_successful_healthcheck_is_not_logged_at_info(json_logs: CapturedLogs) -> None:
    TestClient(make_app()).get("/healthz")
    assert [r for r in json_logs.records() if r["logger"] == "scitracker.access"] == []


def test_failing_healthcheck_is_logged_as_an_error(json_logs: CapturedLogs) -> None:
    def down() -> None:
        raise ConnectionError("db down")

    TestClient(make_app(down)).get("/healthz")
    access = [r for r in json_logs.records() if r["logger"] == "scitracker.access"]
    assert [(r["level"], r["status"]) for r in access] == [("ERROR", 503)]


def test_unexpected_error_is_logged_with_the_id_and_without_secrets(
    json_logs: CapturedLogs,
) -> None:
    app = make_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("db failed, password=hunter2")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    request_id = response.headers["x-request-id"]
    assert response.status_code == 500
    assert "hunter2" not in response.text
    error = next(r for r in json_logs.records() if r["message"].startswith("unhandled error"))
    assert error["request_id"] == request_id
    assert "RuntimeError" in error["exception"]
    assert "hunter2" not in json_logs.text


def test_passwords_and_tokens_never_appear_in_the_logs(
    client: TestClient, json_logs: CapturedLogs
) -> None:
    client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    token = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": PASSWORD}
    ).json()["access_token"]
    client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong-password-1"}
    )
    client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    client.get("/api/v1/me", headers={"Authorization": "Bearer garbage-token-value"})
    assert json_logs.records()  # the access log is there...
    for secret in (PASSWORD, "wrong-password-1", token, "garbage-token-value"):
        assert secret not in json_logs.text  # ...and has no secrets in it
