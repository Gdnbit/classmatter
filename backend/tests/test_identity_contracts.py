from dataclasses import replace
from uuid import uuid4

import httpx
from pydantic import ValidationError
import pytest
from sqlalchemy import text

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.identity_contracts import IdentityChallenge, IdentitySession, IdentityKitSession, IdentitySignedOut
from class_os.interfaces.http.settings import Settings
from test_identity import identity, setup, PASSWORD


def session_body():
    return {"schema_version": "class-os.identity.v1", "csrf_token": "synthetic-" + "a" * 32,
            "subject": {"owner_id": str(uuid4()), "workspace_id": str(uuid4())}}


@pytest.mark.parametrize("mutation", ("missing-version", "empty-csrf", "unknown-token", "unknown-authority", "kit-on-login"))
def test_identity_session_contract_is_closed_and_cannot_fill_missing_authority_fields(mutation):
    body = session_body()
    assert IdentitySession.model_validate(body).subject.owner_id
    if mutation == "missing-version":
        del body["schema_version"]
    elif mutation == "empty-csrf":
        body["csrf_token"] = ""
    elif mutation == "unknown-token":
        body["token"] = "synthetic-token-canary"
    elif mutation == "unknown-authority":
        body["subject"]["administrator"] = True
    else:
        body["recovery_codes"] = []
    with pytest.raises(ValidationError):
        IdentitySession.model_validate(body)


@pytest.mark.parametrize("count", (0, 4, 6))
def test_recovery_kit_response_requires_exactly_five_codes(count):
    body = session_body()
    body["recovery_codes"] = [f"{uuid4()}." + "a" * 32 for _ in range(count)]
    with pytest.raises(ValidationError):
        IdentityKitSession.model_validate(body)


def test_duplicate_kit_and_recovery_subject_are_not_accepted():
    body = session_body()
    code = f"{uuid4()}." + "a" * 32
    body["recovery_codes"] = [code] * 5
    with pytest.raises(ValidationError):
        IdentityKitSession.model_validate(body)
    with pytest.raises(ValidationError):
        IdentityChallenge.model_validate(session_body())
    with pytest.raises(ValidationError):
        IdentitySignedOut.model_validate({"schema_version": "class-os.identity.v1", "status": "administrator"})


def test_different_secrets_cannot_disguise_duplicate_recovery_selectors():
    body = session_body()
    selector = uuid4()
    body["recovery_codes"] = [f"{selector}." + character * 32 for character in "abcde"]
    with pytest.raises(ValidationError, match="Duplicate recovery selector"):
        IdentityKitSession.model_validate(body)


@pytest.mark.db
@pytest.mark.parametrize("fault", ("missing-kit", "invalid-cookie"))
async def test_committed_identity_result_with_invalid_transport_cannot_release_cookie_or_kit(identity, monkeypatch, fault):
    boundary, owner, _ = identity
    setup(boundary)
    original = boundary.reissue_recovery
    def corrupt(*args):
        result = original(*args)  # Actual ISB transaction is already committed.
        return replace(result, recovery_codes=()) if fault == "missing-kit" else replace(result, token="synthetic-invalid-cookie-canary\r\n")
    monkeypatch.setattr(boundary, "reissue_recovery", corrupt)
    app = create_app(Settings(), identity=boundary)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)), base_url="http://127.0.0.1:8000") as client:
        challenge = (await client.get("/api/identity/context")).json()
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": challenge["csrf_token"]}
        logged = await client.post("/api/identity/login", headers=headers, json={"password": PASSWORD})
        headers["x-class-os-csrf"] = logged.json()["csrf_token"]
        before = None
        with owner.transaction(read_only=True) as connection:
            before = connection.execute(text("SELECT code_id FROM class_os.recovery_code ORDER BY code_id")).scalars().all()
        response = await client.post("/api/identity/recovery/reissue", headers=headers, json={"password": PASSWORD})
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "recovery_codes" not in response.text and "canary" not in response.text
        assert not response.headers.get_list("set-cookie")
        assert response.headers["cache-control"] == "no-store"
        assert (await client.get("/api/identity/session")).status_code == 401
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT code_id FROM class_os.recovery_code ORDER BY code_id")).scalars().all() != before
            assert connection.execute(text("SELECT count(*) FROM class_os.identity_audit WHERE action='recovery_reissue' AND outcome='allowed'")).scalar_one() == 1
        # Known password remains a safe route back, never replay plaintext kit.
        challenge = (await client.get("/api/identity/context")).json()
        headers["x-class-os-csrf"] = challenge["csrf_token"]
        assert (await client.post("/api/identity/login", headers=headers, json={"password": PASSWORD})).status_code == 200
