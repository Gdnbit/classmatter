import httpx
import pytest

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_identity import identity, setup, PASSWORD


@pytest.mark.db
async def test_private_identity_lifecycle_routes_reject_stale_csrf_and_revoke_sessions(identity):
    boundary, _, _ = identity
    original = setup(boundary)
    app = create_app(Settings(), identity=boundary)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        challenge = (await client.get("/api/identity/context")).json()
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": challenge["csrf_token"]}
        login = await client.post("/api/identity/login", json={"password": PASSWORD}, headers=headers)
        assert login.status_code == 200
        headers["x-class-os-csrf"] = login.json()["csrf_token"]
        stale = dict(headers)
        body = {"password": PASSWORD}
        assert (await client.post("/api/identity/recovery/reissue", json=body)).status_code == 403
        assert (await client.post("/api/identity/logout-all", json={"password": "wrong-synthetic-password"}, headers=headers)).status_code == 401
        renewed = await client.post("/api/identity/recovery/reissue", json=body, headers=headers)
        assert renewed.status_code == 200 and len(renewed.json()["recovery_codes"]) == 5
        assert "token" not in renewed.json() and renewed.headers["cache-control"] == "no-store"
        assert (await client.post("/api/identity/logout-all", json=body, headers=stale)).status_code == 403
        pre = (await client.get("/api/identity/context")).json()
        rejected = await client.post("/api/identity/recovery/exchange", json={"code": original.recovery_codes[0]},
                                    headers={"origin": headers["origin"], "x-class-os-csrf": pre["csrf_token"]})
        assert rejected.status_code == 401
        headers["x-class-os-csrf"] = renewed.json()["csrf_token"]
        signed_out = await client.post("/api/identity/logout-all", json=body, headers=headers)
        assert signed_out.status_code == 200 and signed_out.json()["status"] == "signed_out_all"
        assert (await client.get("/api/identity/session")).status_code == 401
