from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.identity import IdentityBoundary, IdentityDenied
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.persistence.database import Database, migrate


PASSWORD = "synthetic-test-passphrase-2026"
CLIENT = "synthetic-client-" + "a" * 32


@pytest.fixture
def identity(database_urls):
    owner = Database(database_urls["migrator"], migration=True)
    migrate(owner)
    store = PostgresIdentityStore(Database(database_urls["identity"], identity=True))
    clock = [datetime(2026, 10, 8, 12, tzinfo=timezone.utc)]
    boundary = IdentityBoundary(store, PasswordHash.recommended(), clock=lambda: clock[0])
    try:
        yield boundary, owner, clock
    finally:
        owner.close()
        store.database.close()


def setup(boundary):
    secret = boundary.arm_bootstrap()
    return boundary.bootstrap(secret, PASSWORD, CLIENT)


@pytest.mark.db
def test_bootstrap_session_and_no_plaintext_credentials(identity):
    boundary, owner, _ = identity
    result = setup(boundary)
    subject = boundary.authenticate(result.token, CLIENT, result.csrf)
    assert subject.workspace_id == result.subject.workspace_id
    assert len(result.recovery_codes) == 5
    with owner.transaction(read_only=True) as connection:
        stored = connection.execute(text("SELECT password_hash FROM class_os.owner_account")).scalar_one()
        assert stored.startswith("$argon2id$") and PASSWORD not in stored
        sessions = connection.execute(text("SELECT token_digest, csrf_digest FROM class_os.auth_session")).one()
        assert result.token not in sessions and result.csrf not in sessions
        codes = connection.execute(text("SELECT code_hash FROM class_os.recovery_code")).scalars().all()
        assert all(code.startswith("$argon2id$") for code in codes)
    with pytest.raises(IdentityDenied):
        boundary.arm_bootstrap()
    with pytest.raises(IdentityDenied):
        boundary.bootstrap("invalid", PASSWORD, CLIENT)


@pytest.mark.db
def test_concurrent_bootstrap_can_create_only_one_owner(identity):
    boundary, owner, _ = identity
    secret = boundary.arm_bootstrap()

    def attempt():
        try:
            return boundary.bootstrap(secret, PASSWORD, CLIENT)
        except IdentityDenied:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(item is not None for item in results) == 1
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.owner_account")).scalar_one() == 1


@pytest.mark.db
def test_client_csrf_scope_and_expiry_fail_closed(identity):
    boundary, _, clock = identity
    result = setup(boundary)
    for token, client, csrf in [("unknown", CLIENT, result.csrf), (result.token, "b" * 40, result.csrf),
                                (result.token, CLIENT, "bad")]:
        with pytest.raises(IdentityDenied):
            boundary.authenticate(token, client, csrf)
    with pytest.raises(IdentityDenied):
        boundary.authorize(result.token, CLIENT, str(uuid4()))
    clock[0] += timedelta(hours=2)
    with pytest.raises(IdentityDenied):
        boundary.authenticate(result.token, CLIENT)


@pytest.mark.db
def test_failed_login_is_persistently_limited_and_does_not_enumerate(identity):
    boundary, owner, _ = identity
    setup(boundary)
    for _ in range(6):
        with pytest.raises(IdentityDenied) as failed:
            boundary.login("wrong-password-12345678", CLIENT)
        assert str(failed.value) == "Identity request rejected"
    with pytest.raises(IdentityDenied):
        boundary.login(PASSWORD, CLIENT)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT attempts FROM class_os.identity_rate_limit WHERE action='login'")).scalar_one() == 6
        assert connection.execute(text("SELECT count(*) FROM class_os.identity_audit WHERE outcome='denied'")).scalar_one() >= 6


@pytest.mark.db
def test_logout_and_password_reauthentication(identity):
    boundary, _, clock = identity
    setup(boundary)
    logged = boundary.login(PASSWORD, CLIENT)
    rotated = boundary.reauthenticate(logged.token, CLIENT, logged.csrf, PASSWORD)
    assert rotated.token != logged.token and rotated.csrf != logged.csrf
    with pytest.raises(IdentityDenied):
        boundary.authenticate(logged.token, CLIENT)
    assert boundary.authenticate(rotated.token, CLIENT).reauthenticated_at == clock[0]
    boundary.logout(rotated.token, CLIENT, rotated.csrf)
    with pytest.raises(IdentityDenied):
        boundary.authenticate(rotated.token, CLIENT)


@pytest.mark.db
def test_recovery_bound_client_single_use_and_old_credentials_revoked(identity):
    boundary, _, _ = identity
    old = setup(boundary)
    second = boundary.login(PASSWORD, CLIENT)
    recovery = boundary.exchange_recovery(old.recovery_codes[0], CLIENT)
    with pytest.raises(IdentityDenied):
        boundary.exchange_recovery(old.recovery_codes[0], CLIENT)
    with pytest.raises(IdentityDenied):
        boundary.complete_recovery(recovery.token, "b" * 40, recovery.csrf, "new-synthetic-password-123")
    new = boundary.complete_recovery(recovery.token, CLIENT, recovery.csrf, "new-synthetic-password-123")
    for session in (old, second):
        with pytest.raises(IdentityDenied):
            boundary.authenticate(session.token, CLIENT)
    with pytest.raises(IdentityDenied):
        boundary.complete_recovery(recovery.token, CLIENT, recovery.csrf, "another-synthetic-password")
    with pytest.raises(IdentityDenied):
        boundary.exchange_recovery(old.recovery_codes[1], CLIENT)
    with pytest.raises(IdentityDenied):
        boundary.login(PASSWORD, CLIENT)
    assert boundary.authenticate(new.token, CLIENT).owner_id == old.subject.owner_id
    assert len(new.recovery_codes) == 5
    assert boundary.login("new-synthetic-password-123", CLIENT).subject.owner_id == new.subject.owner_id


@pytest.mark.db
def test_recovery_expiry_and_audit_failure_roll_back(identity, monkeypatch):
    boundary, owner, clock = identity
    original = boundary.store.audit
    secret = boundary.arm_bootstrap()
    monkeypatch.setattr(boundary.store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError, match="audit unavailable"):
        boundary.bootstrap(secret, PASSWORD, CLIENT)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.owner_account")).scalar_one() == 0
    monkeypatch.setattr(boundary.store, "audit", original)
    result = boundary.bootstrap(secret, PASSWORD, CLIENT)
    recovery = boundary.exchange_recovery(result.recovery_codes[0], CLIENT)
    clock[0] += timedelta(minutes=11)
    with pytest.raises(IdentityDenied):
        boundary.complete_recovery(recovery.token, CLIENT, recovery.csrf, "new-synthetic-password-123")


@pytest.mark.db
def test_idle_expiry_bootstrap_expiry_and_scope_denial_are_audited(identity):
    boundary, owner, clock = identity
    secret = boundary.arm_bootstrap()
    clock[0] += timedelta(minutes=10)
    with pytest.raises(IdentityDenied):
        boundary.bootstrap(secret, PASSWORD, CLIENT)
    result = setup(boundary)
    with pytest.raises(IdentityDenied):
        boundary.authorize(result.token, CLIENT, uuid4())
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.identity_audit WHERE action='session' AND outcome='denied'")).scalar_one() == 1
    clock[0] += timedelta(minutes=15)
    with pytest.raises(IdentityDenied):
        boundary.authenticate(result.token, CLIENT)


@pytest.mark.db
def test_identity_and_business_database_privileges_are_separate(identity, database_urls):
    boundary, _, _ = identity
    setup(boundary)
    runtime = Database(database_urls["runtime"])
    try:
        for statement in ["SELECT password_hash FROM class_os.owner_account",
                          "SELECT * FROM class_os.auth_session",
                          "SELECT * FROM class_os.recovery_code"]:
            with pytest.raises(ProgrammingError) as denied, runtime.transaction() as connection:
                connection.execute(text(statement))
            assert denied.value.orig.sqlstate == "42501"
        for statement in ["CREATE TABLE class_os.unapproved (id integer)",
                          "UPDATE class_os.identity_audit SET outcome='allowed'",
                          "DELETE FROM class_os.identity_audit"]:
            with pytest.raises(ProgrammingError) as denied, boundary.store.database.transaction() as connection:
                connection.execute(text(statement))
            assert denied.value.orig.sqlstate == "42501"
    finally:
        runtime.close()
