import logging
from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scitracker.api.app import create_app
from scitracker.api.deps import ReadRepositories
from scitracker.domain.errors import (
    DomainError,
    DuplicateRecordError,
    InvalidStatusTransitionError,
    InvalidValueError,
    RecordNotFoundError,
)

PROBLEM = "urn:scitracker:problem:"


def unused_scope() -> AbstractContextManager[ReadRepositories]:
    raise AssertionError("these tests never touch the repositories")


def ok() -> None:
    return None


def make_app(ping: Callable[[], None] = ok) -> FastAPI:
    return create_app(read_scope=unused_scope, ping=ping)


CASES = [
    (InvalidValueError("bad value"), 422, "invalid-value"),
    (DuplicateRecordError("already there"), 409, "duplicate-record"),
    (RecordNotFoundError("missing"), 404, "not-found"),
    (InvalidStatusTransitionError("to_read", "done", "skip"), 409, "invalid-status-transition"),
    (DomainError("generic"), 400, "domain-error"),
]


@pytest.mark.parametrize(("error", "status", "slug"), CASES)
def test_domain_errors_map_to_stable_problem_types(
    error: DomainError, status: int, slug: str
) -> None:
    app = make_app()

    @app.get("/raise")
    def raise_it() -> None:
        raise error

    response = TestClient(app).get("/raise")
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == f"{PROBLEM}{slug}"
    assert body["status"] == status
    assert body["instance"] == "/raise"


def test_unexpected_error_hides_details_from_the_client_but_logs_them(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = make_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="scitracker.api.problems"):
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == f"{PROBLEM}internal-error"
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
    assert "secret internal detail" in caplog.text


def test_unknown_route_is_a_404_problem() -> None:
    response = TestClient(make_app()).get("/nope")
    assert response.status_code == 404
    assert response.json()["type"] == f"{PROBLEM}not-found"


def test_wrong_method_keeps_the_allow_header() -> None:
    response = TestClient(make_app()).post("/healthz")
    assert response.status_code == 405
    assert response.json()["type"] == f"{PROBLEM}method-not-allowed"
    assert "GET" in response.headers["allow"]


def test_healthz_reports_an_unreachable_database() -> None:
    def down() -> None:
        raise ConnectionError("db password leaked here")

    response = TestClient(make_app(down)).get("/healthz")
    assert response.status_code == 503
    assert response.json()["type"] == f"{PROBLEM}service-unavailable"
    assert "leaked" not in response.text


def test_openapi_describes_endpoints_and_the_problem_schema() -> None:
    spec = TestClient(make_app()).get("/openapi.json").json()
    assert "/api/v1/publications" in spec["paths"]
    assert "/api/v1/publications/{publication_id}" in spec["paths"]
    assert "/healthz" in spec["paths"]
    assert "ProblemDetails" in spec["components"]["schemas"]
