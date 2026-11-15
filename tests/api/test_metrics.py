import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scitracker.api.app import create_app
from scitracker.api.metrics import (
    MetricsAccess,
    MetricsMiddleware,
    MetricsSettings,
)
from scitracker.api.metrics import router as metrics_router
from scitracker.api.problems import register_problem_handlers
from scitracker.observability.metrics import Metrics
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.security.tokens import JwtTokenService
from tests.api.helpers import TEST_SECRET

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _app(metrics: Metrics) -> FastAPI:
    app = FastAPI()
    app.state.metrics = MetricsAccess(metrics, TOKEN)
    register_problem_handlers(app)
    app.add_middleware(MetricsMiddleware, metrics=metrics)
    app.include_router(metrics_router)

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(Metrics()), raise_server_exceptions=False)


def _scrape(client: TestClient) -> str:
    response = client.get("/metrics", headers=AUTH)
    assert response.status_code == 200
    return response.text


def test_request_is_counted(client: TestClient) -> None:
    client.get("/items/1")
    body = _scrape(client)
    assert (
        'scitracker_http_requests_total{method="GET",route="/items/{item_id}",status="200"} 1.0'
        in body
    )


def test_route_label_is_template(client: TestClient) -> None:
    for item_id in (1, 2, 3):
        client.get(f"/items/{item_id}")
    body = _scrape(client)
    assert 'route="/items/{item_id}",status="200"} 3.0' in body
    assert 'route="/items/1"' not in body


def test_unknown_paths_share_one_label(client: TestClient) -> None:
    client.get("/nope-1")
    client.get("/nope-2")
    body = _scrape(client)
    assert 'route="unmatched",status="404"} 2.0' in body
    assert "nope-1" not in body


def test_unhandled_error_is_counted_as_500(client: TestClient) -> None:
    assert client.get("/boom").status_code == 500
    assert 'route="/boom",status="500"} 1.0' in _scrape(client)


def test_duration_histogram_is_exposed(client: TestClient) -> None:
    client.get("/items/1")
    assert "scitracker_http_request_duration_seconds_bucket" in _scrape(client)


def test_in_progress_returns_to_zero(client: TestClient) -> None:
    client.get("/items/1")
    # the scrape request itself is in progress while the registry is rendered
    assert "scitracker_http_requests_in_progress 1.0" in _scrape(client)


def test_scrape_requires_token(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": f"Basic {TOKEN}"}).status_code == 401


def test_unauthorized_scrape_does_not_leak_metrics(client: TestClient) -> None:
    body = client.get("/metrics").text
    assert "scitracker_http" not in body


def test_metrics_endpoint_is_hidden_from_openapi(client: TestClient) -> None:
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def test_disabled_metrics_are_not_served() -> None:
    app = create_app(
        scope=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        ping=lambda: None,
        hasher=Argon2PasswordHasher(),
        tokens=JwtTokenService(TEST_SECRET),
    )
    assert TestClient(app).get("/metrics", headers=AUTH).status_code == 404


def test_create_app_counts_healthz() -> None:
    app = create_app(
        scope=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        ping=lambda: None,
        hasher=Argon2PasswordHasher(),
        tokens=JwtTokenService(TEST_SECRET),
        metrics=MetricsAccess(Metrics(), TOKEN),
    )
    with TestClient(app) as test_client:
        assert test_client.get("/healthz").status_code == 200
        body = test_client.get("/metrics", headers=AUTH).text
    assert 'route="/healthz",status="200"} 1.0' in body


def test_registries_are_isolated_between_apps() -> None:
    first, second = Metrics(), Metrics()
    TestClient(_app(first)).get("/items/1")
    assert b"items" in first.render()
    assert b"items" not in second.render()


def test_settings_default_is_disabled() -> None:
    settings = MetricsSettings.from_env({})
    assert (settings.enabled, settings.token) == (False, "")


def test_settings_enabled_with_token() -> None:
    settings = MetricsSettings.from_env({"METRICS_ENABLED": "true", "METRICS_TOKEN": TOKEN})
    assert (settings.enabled, settings.token) == (True, TOKEN)


@pytest.mark.parametrize("token", ["", "short"])
def test_enabled_without_strong_token_is_rejected(token: str) -> None:
    with pytest.raises(ValueError, match="METRICS_TOKEN must be at least 16"):
        MetricsSettings.from_env({"METRICS_ENABLED": "true", "METRICS_TOKEN": token})


def test_error_message_does_not_contain_token() -> None:
    with pytest.raises(ValueError, match="METRICS_TOKEN") as info:
        MetricsSettings.from_env({"METRICS_ENABLED": "1", "METRICS_TOKEN": "secret"})
    assert "secret" not in str(info.value)


def test_create_app_uses_full_route_template() -> None:
    app = create_app(
        scope=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        ping=lambda: None,
        hasher=Argon2PasswordHasher(),
        tokens=JwtTokenService(TEST_SECRET),
        metrics=MetricsAccess(Metrics(), TOKEN),
    )
    with TestClient(app) as test_client:
        test_client.get("/api/v1/auth/login")
        body = test_client.get("/metrics", headers=AUTH).text
    assert 'route="/api/v1/auth/login"' in body
