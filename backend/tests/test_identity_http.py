import httpx
import pytest

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_identity import identity, PASSWORD


@pytest.mark.db
async def test_identity_http_cookie_csrf_origin_and_recovery(identity):
    boundary, _, _ = identity
    secret = boundary.arm_bootstrap()
    transport = httpx.ASGITransport(app=create_app(Settings(), identity=boundary), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        context = await client.get("/api/identity/context")
        csrf = context.json()["csrf_token"]
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": csrf}
        assert (await client.post("/api/identity/bootstrap", json={"secret": secret, "password": PASSWORD})).status_code == 403
        setup = await client.post("/api/identity/bootstrap", json={"secret": secret, "password": PASSWORD}, headers=headers)
        assert setup.status_code == 200
        assert "token" not in setup.json()
        assert "httponly" in setup.headers.get_list("set-cookie")[0].lower()
        assert all("samesite=strict" in cookie.lower() for cookie in setup.headers.get_list("set-cookie"))
        assert setup.headers["cache-control"] == "no-store"
        codes = setup.json()["recovery_codes"]
        current = await client.get("/api/identity/session")
        assert current.status_code == 200
        csrf = current.json()["csrf_token"]
        headers["x-class-os-csrf"] = csrf
        assert (await client.post("/api/identity/logout", headers={"origin": headers["origin"]})).status_code == 403
        assert (await client.post("/api/identity/reauthenticate", json={"password": PASSWORD}, headers=headers)).status_code == 200
        current = await client.get("/api/identity/session")
        headers["x-class-os-csrf"] = current.json()["csrf_token"]
        assert (await client.post("/api/identity/logout", headers=headers)).status_code == 200
        assert (await client.get("/api/identity/session")).status_code == 401
        context = await client.get("/api/identity/context")
        headers["x-class-os-csrf"] = context.json()["csrf_token"]
        exchange = await client.post("/api/identity/recovery/exchange", json={"code": codes[0]}, headers=headers)
        assert exchange.status_code == 200
        # Recovery capability cannot authenticate a business session.
        assert (await client.get("/api/identity/session")).status_code == 401
        headers["x-class-os-csrf"] = exchange.json()["csrf_token"]
        complete = await client.post("/api/identity/recovery/complete", json={"password": "new-synthetic-password-123"}, headers=headers)
        assert complete.status_code == 200
        assert len(complete.json()["recovery_codes"]) == 5
        assert (await client.get("/api/identity/session")).status_code == 200


@pytest.mark.db
async def test_identity_http_rejects_body_and_redacts_errors(identity):
    boundary, _, _ = identity
    transport = httpx.ASGITransport(app=create_app(Settings(), identity=boundary), client=("127.0.0.1", 12345), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        context = await client.get("/api/identity/context")
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": context.json()["csrf_token"]}
        for body in [{"password": "credential-do-not-echo", "administrator": True},
                     {"password": "x" * 9000}]:
            response = await client.post("/api/identity/login", json=body, headers=headers)
            assert response.status_code == 400
            assert "credential" not in response.text
            assert response.headers["cache-control"] == "no-store"
        response = await client.post("/api/identity/login", json={"password": "credential-do-not-echo"}, headers=headers)
        assert response.status_code == 401
        assert "credential" not in response.text
        for raw in ['{"password":"first-value-123456","password":"second-value-123456"}',
                    '{"password":NaN}', '{"password":' + '[' * 2000]:
            response = await client.post("/api/identity/login", content=raw,
                                        headers={**headers, "content-type": "application/json"})
            assert response.status_code == 400
            assert "password" not in response.text
