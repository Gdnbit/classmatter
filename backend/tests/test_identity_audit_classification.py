"""ISB audit receipts remain inside its own transaction and authority."""
import asyncio
import traceback
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable, require_audit
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_identity import identity, setup, CLIENT, PASSWORD
from test_identity_operation_receipt import ACTIONS, prepare
from test_identity_mutation_receipt import snapshot
from test_roster_gateway import roster, class_command


def test_shared_audit_check_preserves_valid_receipt_and_calls_writer_once():
    receipt, calls = uuid4(), []
    def write(*args):
        calls.append(args)
        return receipt
    assert require_audit(write, "synthetic-action") == receipt
    assert calls == [("synthetic-action",)]


def test_shared_audit_check_suppresses_raw_exception_in_traceback_and_signal(caplog):
    def failed():
        raise RuntimeError("synthetic-private-audit-trace-canary")
    with pytest.raises(AuditUnavailable) as failure:
        require_audit(failed)
    rendered = "".join(traceback.format_exception(failure.value))
    assert "synthetic-private-audit-trace-canary" not in rendered + caplog.text
    assert failure.value.__suppress_context__ is True
    assert len(caplog.records) == 1 and caplog.records[0].exc_info is None


def test_shared_audit_check_does_not_reclassify_cancellation(caplog):
    cancellation = asyncio.CancelledError()
    def cancelled():
        raise cancellation
    with pytest.raises(asyncio.CancelledError) as failure:
        require_audit(cancelled)
    assert failure.value is cancellation and caplog.records == []


@pytest.mark.db
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("method", ("operation_audit", "audit"))
def test_missing_identity_audit_rolls_back_security_effects_and_original_key_can_recover(identity, monkeypatch, action, method):
    boundary, owner, _ = identity
    token, csrf, call = prepare(boundary, action)
    operation = uuid4()
    before = snapshot(owner)
    original = getattr(boundary.store, method)
    monkeypatch.setattr(boundary.store, method, lambda *args: None)
    with pytest.raises(AuditUnavailable, match="audit unavailable"), boundary.operation(action, operation, CLIENT, csrf, token):
        call()
    assert snapshot(owner) == before
    monkeypatch.setattr(boundary.store, method, original)
    with boundary.operation(action, operation, CLIENT, csrf, token):
        call()
    assert boundary.operation_status(action, operation, CLIENT, csrf) == "committed"


@pytest.mark.db
def test_missing_logout_receipt_cannot_revoke_or_acknowledge_a_session(identity, monkeypatch):
    boundary, owner, _ = identity
    result = setup(boundary)
    before = snapshot(owner)
    monkeypatch.setattr(boundary.store, "logout_audit", lambda *args: None)
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        boundary.logout(result.token, CLIENT, result.csrf, uuid4())
    assert snapshot(owner) == before


@pytest.mark.db
def test_invalid_authorization_audit_never_enters_business_and_releases_lock(roster, monkeypatch):
    business, _, store, credentials, boundary, owner, _ = roster
    def forbidden():
        pytest.fail("Business transaction entered without a durable ISB audit")
    monkeypatch.setattr(store, "atomic", forbidden)
    monkeypatch.setattr(boundary.store, "audit", lambda *args: "synthetic-invalid-receipt")
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        business.preview(*credentials, class_command())
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal")).scalar_one() == 0
        assert connection.execute(text("SELECT pg_try_advisory_xact_lock(607103018)")).scalar_one() is True


@pytest.mark.db
@pytest.mark.parametrize("fault", ("missing", "exception"))
async def test_login_audit_fault_returns_closed_503_without_secret_or_cookie(identity, monkeypatch, caplog, fault):
    boundary, owner, _ = identity
    setup(boundary)
    app = create_app(Settings(), identity=boundary)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345),
                                                            raise_app_exceptions=True),
                                 base_url="http://127.0.0.1:8000") as client:
        challenge = (await client.get("/api/identity/context")).json()
        before = snapshot(owner)
        def failed(*args):
            if fault == "exception":
                raise RuntimeError("synthetic-private-identity-audit-canary")
            return None
        monkeypatch.setattr(boundary.store, "audit", failed)
        response = await client.post("/api/identity/login", json={"password": PASSWORD, "request_id": str(uuid4())},
                                     headers={"origin": "http://127.0.0.1:8000", "x-class-os-csrf": challenge["csrf_token"]})
    assert response.status_code == 503
    assert response.json() == {"schema_version": "class-os.error.v1", "request_id": response.headers["x-request-id"],
                               "error": {"code": "AUDIT_UNAVAILABLE", "message": "Request rejected."}}
    assert not response.headers.get_list("set-cookie") and response.headers["cache-control"] == "no-store"
    assert snapshot(owner) == before
    assert "synthetic-private-identity-audit-canary" not in response.text + caplog.text
    signals = [record for record in caplog.records if record.name == "class_os.security"]
    assert len(signals) == 1 and signals[0].exc_info is None
    assert signals[0].getMessage() == "audit_unavailable kind=audit-unavailable"
