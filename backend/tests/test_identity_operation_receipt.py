from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
import httpx
from dataclasses import replace
from sqlalchemy import text

from class_os.application.identity import IdentityAlreadyCommitted, IdentityDenied
from test_identity import identity, setup, CLIENT, PASSWORD
from test_identity_mutation_receipt import snapshot
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings


ACTIONS = ("bootstrap", "login", "reauthenticate", "logout_all", "recovery_reissue", "recovery_exchange", "recovery_complete")


def prepare(boundary, action):
    csrf = "synthetic-pre-csrf-" + "a" * 32
    if action == "bootstrap":
        secret = boundary.arm_bootstrap()
        return None, csrf, lambda: boundary.bootstrap(secret, PASSWORD, CLIENT)
    original = setup(boundary)
    if action == "login":
        return None, csrf, lambda: boundary.login(PASSWORD, CLIENT)
    if action == "recovery_exchange":
        return None, csrf, lambda: boundary.exchange_recovery(original.recovery_codes[0], CLIENT)
    if action == "recovery_complete":
        recovery = boundary.exchange_recovery(original.recovery_codes[0], CLIENT)
        return recovery.token, recovery.csrf, lambda: boundary.complete_recovery(recovery.token, CLIENT, recovery.csrf, PASSWORD + "-new")
    methods = {"reauthenticate": boundary.reauthenticate, "logout_all": boundary.logout_all,
               "recovery_reissue": boundary.reissue_recovery}
    return original.token, original.csrf, lambda: methods[action](original.token, CLIENT, original.csrf, PASSWORD)


@pytest.mark.db
@pytest.mark.parametrize("action", ACTIONS)
def test_identity_operation_receipt_no_replayed_secrets_or_mutations(identity, action):
    boundary, owner, clock = identity
    token, csrf, call = prepare(boundary, action)
    operation = uuid4()
    with boundary.operation(action, operation, CLIENT, csrf, token):
        result = call()
    assert boundary.operation_status(action, operation, CLIENT, csrf) == "committed"
    with pytest.raises(IdentityAlreadyCommitted), boundary.operation(action, operation, CLIENT, csrf, token):
        call()
    for client, proof in ((CLIENT + "b", csrf), (CLIENT, "b" * 40)):
        with pytest.raises(IdentityDenied):
            boundary.operation_status(action, operation, client, proof)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.identity_audit WHERE request_id=:id"), {"id": operation}).scalar_one() == 1
    if result is not None:
        assert result.token not in str(boundary.operation_status(action, operation, CLIENT, csrf))
    clock[0] += timedelta(minutes=10)
    with pytest.raises(IdentityDenied):
        boundary.operation_status(action, operation, CLIENT, csrf)


@pytest.mark.db
def test_same_identity_request_never_executes_changed_password_or_concurrent_duplicate(identity):
    boundary, owner, _ = identity
    token, csrf, call = prepare(boundary, "login")
    operation = uuid4()
    def attempt(_):
        try:
            with boundary.operation("login", operation, CLIENT, csrf, token):
                call()
            return True
        except IdentityAlreadyCommitted:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(attempt, range(2))) == 1
    with pytest.raises(IdentityAlreadyCommitted), boundary.operation("login", operation, CLIENT, csrf, token):
        boundary.login(PASSWORD + "wrong", CLIENT)
    # Context reset: a separately requested login receives its own result.
    assert boundary.login(PASSWORD, CLIENT).subject


@pytest.mark.db
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("fault", ("receipt", "final-audit"))
def test_identity_receipt_and_final_audit_fault_roll_back_every_security_effect(identity, monkeypatch, action, fault):
    boundary, owner, _ = identity
    token, csrf, call = prepare(boundary, action)
    operation = uuid4()
    before = snapshot(owner)
    method = "operation_audit" if fault == "receipt" else "audit"
    original = getattr(boundary.store, method)
    def failed(*args):
        raise RuntimeError("Synthetic metadata persistence outage")
    monkeypatch.setattr(boundary.store, method, failed)
    with pytest.raises(RuntimeError), boundary.operation(action, operation, CLIENT, csrf, token):
        call()
    assert snapshot(owner) == before
    monkeypatch.setattr(boundary.store, method, original)
    with boundary.operation(action, operation, CLIENT, csrf, token):
        call()
    assert boundary.operation_status(action, operation, CLIENT, csrf) == "committed"


@pytest.mark.db
def test_identity_suppressed_receipt_cannot_release_secret_result(identity):
    boundary, owner, _ = identity
    token, csrf, call = prepare(boundary, "login")
    before = snapshot(owner)
    with owner.transaction() as connection:
        connection.execute(text("CREATE FUNCTION class_os.skip_operation_fixture() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN IF NEW.request_id IS NOT NULL THEN RETURN NULL; END IF; RETURN NEW; END'"))
        connection.execute(text("CREATE TRIGGER skip_operation_fixture BEFORE INSERT ON class_os.identity_audit FOR EACH ROW EXECUTE FUNCTION class_os.skip_operation_fixture()"))
    with pytest.raises(RuntimeError), boundary.operation("login", uuid4(), CLIENT, csrf, token):
        call()
    assert snapshot(owner) == before


@pytest.mark.db
async def test_http_lost_kit_delivers_only_nonreplayable_metadata_and_duplicate_is_conflict(identity, monkeypatch):
    boundary, owner, _ = identity
    setup(boundary)
    app = create_app(Settings(), identity=boundary)
    original = boundary.reissue_recovery
    calls = []
    def lost(*args):
        calls.append(True)
        return replace(original(*args), recovery_codes=())
    monkeypatch.setattr(boundary, "reissue_recovery", lost)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://127.0.0.1:8000") as client:
        context = (await client.get("/api/identity/context")).json()
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": context["csrf_token"]}
        login = (await client.post("/api/identity/login", json={"password": PASSWORD}, headers=headers)).json()
        headers["x-class-os-csrf"] = login["csrf_token"]
        operation = str(uuid4())
        body = {"password": PASSWORD, "request_id": operation}
        assert (await client.post("/api/identity/recovery/reissue", json=body, headers=headers)).status_code == 500
        path = f"/api/identity/receipts/recovery_reissue/{operation}"
        assert (await client.get(path)).status_code == 403
        metadata = await client.get(path, headers=headers)
        assert not metadata.headers.get_list("set-cookie")
        assert metadata.json() == {"schema_version": "class-os.identity-operation-receipt.v1",
            "request_id": operation, "action": "recovery_reissue", "status": "committed", "result_replayable": False}
        assert (await client.get(path.replace("recovery_reissue", "login"), headers=headers)).status_code == 401
        duplicate = await client.post("/api/identity/recovery/reissue", json={**body, "password": PASSWORD + "-wrong"}, headers=headers)
        assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "identity_already_committed"
        assert len(calls) == 2  # HTTP wrapper called again, ISB callback never reissued.
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.identity_audit WHERE request_id=:id"), {"id": operation}).scalar_one() == 1
        assert (await client.get("/api/identity/session")).status_code == 401
