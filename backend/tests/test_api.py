"""T-RPLT-001/002 development subslice; not release admission evidence."""
import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings


async def request(path="/health/live", *, method="GET", headers=None, peer="127.0.0.1", app=None):
    transport = httpx.ASGITransport(app=app or create_app(Settings()), client=(peer, 12345), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        return await client.request(method, path, headers=headers)


async def test_live_contract_and_server_owned_correlation():
    response = await request(headers={"x-request-id": "untrusted-value"})
    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "class-os.health.v1", "service": "class-os-api",
        "mode": "synthetic-development", "status": "alive",
    }
    UUID(response.headers["x-request-id"])
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "access-control-allow-origin" not in response.headers


async def test_readiness_is_not_faked():
    response = await request("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["components"] == {
        "database": "not_configured", "identity": "not_configured", "business_gateways": "not_configured",
    }
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("headers,peer", [
    ({"host": "evil.example:8000"}, "127.0.0.1"),
    ({"host": "127.0.0.1:9000"}, "127.0.0.1"),
    ({"forwarded": "for=127.0.0.1"}, "127.0.0.1"),
    ({"x-forwarded-for": "127.0.0.1"}, "127.0.0.1"),
    ({"x-forwarded-proto": "http"}, "127.0.0.1"),
    ({"origin": "https://evil.example"}, "127.0.0.1"),
    ({}, "192.0.2.1"), ({}, "not-an-ip"),
    ([("host", "127.0.0.1:8000"), ("host", "evil.example")], "127.0.0.1"),
])
async def test_local_boundary_rejects_forgery(headers, peer):
    response = await request(headers=headers, peer=peer)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "local_boundary_rejected"
    assert "evil.example" not in response.text


@pytest.mark.parametrize("path,method,status,code", [
    ("/health/live?secret=do-not-echo", "GET", 400, "invalid_request"),
    ("/missing-sensitive-path", "GET", 404, "not_found"),
    ("/health/live", "POST", 405, "method_not_allowed"),
    ("/docs", "GET", 404, "not_found"),
    ("/openapi.json", "GET", 404, "not_found"),
])
async def test_errors_are_static_and_versioned(path, method, status, code):
    response = await request(path, method=method)
    assert response.status_code == status
    body = response.json()
    assert body["schema_version"] == "class-os.error.v1"
    assert body["error"]["code"] == code
    assert body["request_id"] == response.headers["x-request-id"]
    assert "secret" not in response.text
    assert "sensitive-path" not in response.text
    assert response.headers["cache-control"] == "no-store"


async def test_unhandled_exception_does_not_leak():
    app = create_app(Settings())

    @app.get("/test-only-fault")
    def fault():
        raise RuntimeError("credential-do-not-echo")

    response = await request("/test-only-fault", app=app)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "credential" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("overrides", [
    {"mode": "production"}, {"bind_host": "0.0.0.0"}, {"model_provider": "openai"},
    {"port": 0}, {"port": 65536}, {"port": True},
])
def test_settings_fail_closed(overrides):
    with pytest.raises(ValueError):
        Settings(**overrides)


def test_env_is_explicit_and_rejects_unsupported_mode():
    settings = Settings.from_env({"CLASS_OS_PORT": "8100", "UNRELATED_SECRET": "never-read"})
    assert settings.port == 8100
    with pytest.raises(ValueError, match="Invalid backend settings"):
        Settings.from_env({"CLASS_OS_MODE": "credential-do-not-echo"})


def test_only_health_routes_exist_and_docs_are_disabled():
    app = create_app(Settings())
    assert {route.path for route in app.routes} == {"/health/live", "/health/ready"}
    assert not app.debug
    assert app.openapi_url is None


def test_versioned_contracts_match_models():
    from class_os.interfaces.http.contracts import ErrorResponse, LiveResponse, ReadyResponse
    root = Path(__file__).resolve().parents[2] / "contracts/http"
    for name, model in [("health-live.v1", LiveResponse), ("health-ready.v1", ReadyResponse), ("error.v1", ErrorResponse)]:
        assert json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8")) == model.model_json_schema()
