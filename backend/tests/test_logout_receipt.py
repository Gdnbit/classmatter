from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.identity import IdentityDenied
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.persistence.database import Database
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_identity import identity, setup, CLIENT, PASSWORD


@pytest.mark.db
def test_logout_receipt_atomic_replay_restart_scope_and_expiry(identity):
    boundary, owner, clock = identity
    result = setup(boundary)
    operation = uuid4()
    boundary.logout(result.token, CLIENT, result.csrf, operation)
    fresh = boundary.login(PASSWORD, CLIENT)
    boundary.logout(result.token, CLIENT, result.csrf, operation)
    assert boundary.authenticate(fresh.token, CLIENT, fresh.csrf)
    assert boundary.logout_status(operation, CLIENT, result.csrf) == "committed"
    assert boundary.logout_status(uuid4(), CLIENT, result.csrf) == "not_committed"
    boundary.logout(result.token, CLIENT, result.csrf, operation)
    with pytest.raises(IdentityDenied):
        boundary.authenticate(result.token, CLIENT, result.csrf)
    for client, csrf in ((CLIENT + "b", result.csrf), (CLIENT, "b" * 40)):
        with pytest.raises(IdentityDenied):
            boundary.logout_status(operation, client, csrf)
    with owner.transaction(read_only=True) as connection:
        row = connection.execute(text("SELECT count(*) FROM class_os.identity_audit WHERE request_id=:id"), {"id": operation}).scalar_one()
        assert row == 1
    boundary.store = PostgresIdentityStore(boundary.store.database)
    assert boundary.logout_status(operation, CLIENT, result.csrf) == "committed"
    clock[0] += timedelta(minutes=10)
    with pytest.raises(IdentityDenied):
        boundary.logout_status(operation, CLIENT, result.csrf)


@pytest.mark.db
def test_logout_receipt_audit_outage_rolls_back_and_concurrent_retry_once(identity, monkeypatch):
    boundary, owner, _ = identity
    result = setup(boundary)
    operation = uuid4()
    original = boundary.store.logout_audit
    monkeypatch.setattr(boundary.store, "logout_audit", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic")))
    with pytest.raises(RuntimeError):
        boundary.logout(result.token, CLIENT, result.csrf, operation)
    assert boundary.authenticate(result.token, CLIENT, result.csrf)
    assert boundary.logout_status(operation, CLIENT, result.csrf) == "not_committed"
    monkeypatch.setattr(boundary.store, "logout_audit", original)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: boundary.logout(result.token, CLIENT, result.csrf, operation), range(2))) == [None, None]
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.identity_audit WHERE request_id=:id"), {"id": operation}).scalar_one() == 1


@pytest.mark.db
@pytest.mark.parametrize("lose_response", (False, True))
async def test_logout_receipt_http_closed_private_and_postcommit_loss(identity, monkeypatch, lose_response):
    boundary, _, _ = identity
    setup(boundary)
    app = create_app(Settings(), identity=boundary)
    original = boundary.logout
    calls = []
    def lost(*args):
        calls.append(True)
        original(*args)
        if lose_response:
            raise RuntimeError("Synthetic postcommit delivery outage")
    monkeypatch.setattr(boundary, "logout", lost)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://127.0.0.1:8000") as client:
        challenge = (await client.get("/api/identity/context")).json()
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": challenge["csrf_token"]}
        logged = (await client.post("/api/identity/login", json={"password": PASSWORD}, headers=headers)).json()
        headers["x-class-os-csrf"] = logged["csrf_token"]
        operation = str(uuid4())
        response = await client.post("/api/identity/logout", json={"request_id": operation}, headers=headers)
        assert response.status_code == (500 if lose_response else 200)
        if not lose_response:
            assert "class_os_session" not in client.cookies and "class_os_csrf" not in client.cookies
        path = f"/api/identity/logout/receipts/{operation}"
        assert (await client.get(path)).status_code == 403
        receipt = await client.get(path, headers=headers)
        assert receipt.json() == {"schema_version": "class-os.identity-logout-receipt.v1", "request_id": operation, "action": "logout", "status": "committed"}
        assert len(calls) == 1 and (await client.get("/api/identity/session")).status_code == 401
        assert (await client.post("/api/identity/logout", json={"request_id": operation, "unknown": True}, headers=headers)).status_code == 400


@pytest.mark.db
def test_logout_suppressed_receipt_rolls_back_session(identity):
    boundary, owner, _ = identity
    result = setup(boundary)
    with owner.transaction() as connection:
        connection.execute(text("CREATE FUNCTION class_os.skip_logout_fixture() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN IF NEW.request_id IS NOT NULL THEN RETURN NULL; END IF; RETURN NEW; END'"))
        connection.execute(text("CREATE TRIGGER skip_logout_fixture BEFORE INSERT ON class_os.identity_audit FOR EACH ROW EXECUTE FUNCTION class_os.skip_logout_fixture()"))
    with pytest.raises(RuntimeError):
        boundary.logout(result.token, CLIENT, result.csrf, uuid4())
    assert boundary.authenticate(result.token, CLIENT, result.csrf)


@pytest.mark.db
def test_logout_status_audit_outage_and_runtime_denial(identity, database_urls, monkeypatch):
    boundary, _, _ = identity
    result = setup(boundary)
    operation = uuid4()
    boundary.logout(result.token, CLIENT, result.csrf, operation)
    original = boundary.store.audit
    def failed(connection, action, outcome, now):
        if action == "logout_status":
            raise RuntimeError("synthetic-audit-outage")
        return original(connection, action, outcome, now)
    monkeypatch.setattr(boundary.store, "audit", failed)
    with pytest.raises(RuntimeError):
        boundary.logout_status(operation, CLIENT, result.csrf)
    runtime = Database(database_urls["runtime"])
    try:
        with pytest.raises(ProgrammingError) as denied, runtime.transaction(read_only=True) as connection:
            connection.execute(text("SELECT request_id FROM class_os.identity_audit"))
        assert denied.value.orig.sqlstate == "42501"
    finally:
        runtime.close()
    with boundary.store.database.transaction(read_only=True) as connection:
        assert not connection.execute(text("SELECT has_table_privilege(current_user,'class_os.identity_audit','UPDATE')")).scalar_one()
        assert not connection.execute(text("SELECT has_table_privilege(current_user,'class_os.identity_audit','DELETE')")).scalar_one()
