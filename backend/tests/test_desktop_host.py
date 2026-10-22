import hashlib
import hmac

import httpx
import pytest

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.desktop_host import install_desktop_proof


@pytest.mark.asyncio
async def test_proof_is_opt_in_closed_and_not_readiness_or_authorization():
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        assert (await client.get("/health/desktop")).status_code == 404
        key = "12" * 32
        install_desktop_proof(app, key)
        assert (await client.get("/health/desktop")).status_code == 400
        challenge = "34" * 32
        response = await client.get("/health/desktop", headers={"x-classmatter-challenge": challenge})
        assert response.json() == {"schema_version": "classmatter.desktop-proof.v1", "mode": "synthetic-only", "challenge": challenge,
                                   "proof": hmac.new(bytes.fromhex(key), ("classmatter.desktop.v1:" + challenge).encode(), hashlib.sha256).hexdigest()}
        assert response.headers["cache-control"] == "no-store"
        assert key not in response.text
        assert (await client.get("/health/ready")).status_code == 503
        assert (await client.post("/api/workspaces/unowned/commands/commit", json={})).status_code == 404
        assert (await client.get("/health/desktop", headers=[("x-classmatter-challenge", challenge)] * 2)).status_code == 400
        assert (await client.get("/health/desktop", headers={"x-classmatter-challenge": challenge, "origin": "https://untrusted.invalid"})).status_code == 403


@pytest.mark.parametrize("key", [None, "", "12", "g" * 64, "A" * 64])
def test_invalid_process_keys_fail_before_serving(key):
    with pytest.raises(ValueError):
        install_desktop_proof(create_app(Settings()), key)
