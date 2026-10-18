from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.identity import IdentityDenied
from test_roster_gateway import roster, class_command, create_class
from class_os.domain.roster import CreateStudent
from test_identity import identity, CLIENT


@pytest.mark.db
def test_authorized_business_operation_holds_actual_revocation_lock_until_done(roster, monkeypatch):
    gateway, query, store, credentials, boundary, _, _ = roster
    proposal = gateway.preview(*credentials, class_command())
    proof = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    entered, release = Event(), Event()
    original = store.atomic

    @contextmanager
    def paused():
        entered.set()
        assert release.wait(5), "Owned synchronization barrier timed out"
        with original() as transaction:
            yield transaction

    monkeypatch.setattr(store, "atomic", paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(gateway.commit, *credentials, proposal.proposal_id, uuid4(), proof)
        try:
            assert entered.wait(3)
            # Observe the actual database lock, not a runtime flag/receipt.
            with boundary.store.database.transaction() as connection:
                available = connection.execute(text("SELECT pg_try_advisory_xact_lock(607103018)")).scalar_one()
            assert available is False
        finally:
            release.set()
        assert future.result(timeout=5).version == 1
    monkeypatch.setattr(store, "atomic", original)
    with boundary.store.database.transaction() as connection:
        assert connection.execute(text("SELECT pg_try_advisory_xact_lock(607103018)")).scalar_one() is True
    boundary.logout(*credentials[:3])
    with pytest.raises(IdentityDenied):
        query.context(*credentials)


@pytest.mark.db
def test_guard_releases_actual_lock_on_business_exception(roster, monkeypatch):
    _, query, store, credentials, boundary, _, _ = roster

    @contextmanager
    def broken():
        raise RuntimeError("Synthetic business outage")
        yield

    monkeypatch.setattr(store, "atomic", broken)
    with pytest.raises(RuntimeError, match="Synthetic business outage"):
        query.context(*credentials)
    with boundary.store.database.transaction() as connection:
        assert connection.execute(text("SELECT pg_try_advisory_xact_lock(607103018)")).scalar_one() is True
    # ISB remains usable; no stranded connection/session lock.
    boundary.logout(*credentials[:3])


@pytest.mark.db
def test_authorization_audit_failure_prevents_business_entry_and_releases_lock(roster, monkeypatch):
    gateway, _, store, credentials, boundary, owner, _ = roster

    def audit_failure(*args):
        raise RuntimeError("Synthetic identity audit outage")

    def forbidden():
        pytest.fail("Business transaction entered before durable authorization audit")

    monkeypatch.setattr(boundary.store, "audit", audit_failure)
    monkeypatch.setattr(store, "atomic", forbidden)
    from class_os.application.audit import AuditUnavailable
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        gateway.preview(*credentials, class_command())
    with owner.transaction() as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal")).scalar_one() == 0
        assert connection.execute(text("SELECT pg_try_advisory_xact_lock(607103018)")).scalar_one() is True


@pytest.mark.db
def test_revocation_commits_before_waiting_request_authorizes(roster):
    gateway, _, _, credentials, boundary, owner, _ = roster
    attempted = Event()

    def preview():
        attempted.set()
        return gateway.preview(*credentials, class_command())

    with ThreadPoolExecutor(max_workers=1) as pool:
        with boundary.store.database.identity_lease() as connection:
            with connection.begin():
                connection.execute(text("UPDATE class_os.auth_session SET revoked_at=last_seen_at WHERE revoked_at IS NULL"))
            future = pool.submit(preview)
            assert attempted.wait(2)
        with pytest.raises(IdentityDenied):
            future.result(timeout=5)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal")).scalar_one() == 0
        assert connection.execute(text("SELECT outcome FROM class_os.identity_audit ORDER BY occurred_at DESC,event_id")).scalars().all().count("denied") == 1


@pytest.mark.db
def test_waiting_for_authorization_does_not_extend_idle_session(roster, monkeypatch):
    _, query, _, credentials, boundary, _, clock = roster
    original = boundary.store.authorization_guard

    @contextmanager
    def delayed(callback):
        clock[0] += timedelta(minutes=16)
        with original(callback) as result:
            yield result

    monkeypatch.setattr(boundary.store, "authorization_guard", delayed)
    with pytest.raises(IdentityDenied):
        query.context(*credentials)


@pytest.mark.db
def test_identity_clock_is_evaluated_after_identity_transaction_lock(roster, monkeypatch):
    _, _, _, credentials, boundary, _, clock = roster
    original = boundary.store.atomic

    @contextmanager
    def delayed():
        with original() as tx:
            clock[0] += timedelta(minutes=16)
            yield tx

    monkeypatch.setattr(boundary.store, "atomic", delayed)
    with pytest.raises(IdentityDenied):
        boundary.authenticate(*credentials[:2], csrf=credentials[2])


@pytest.mark.db
@pytest.mark.parametrize("operation", ["read", "preview", "commit"])
def test_business_lock_wait_cannot_extend_absolute_session_expiry(roster, monkeypatch, operation):
    gateway, query, store, credentials, _, owner, clock = roster
    classroom, _ = create_class(gateway, credentials)
    clock[0] += timedelta(minutes=59, seconds=59)
    # Keep idle expiry out of this test: the absolute deadline is still fixed.
    with owner.transaction() as connection:
        connection.execute(text("UPDATE class_os.auth_session SET last_seen_at=:now"), {"now": clock[0]})
    student = CreateStudent(uuid4(), classroom.class_id, classroom.term_id, 1, "合成期限学生")
    proposal = gateway.preview(*credentials, student) if operation == "commit" else None
    original = store.atomic

    @contextmanager
    def delayed():
        with original() as transaction:
            clock[0] += timedelta(seconds=1)  # Exactly expires_at, not just after.
            yield transaction

    monkeypatch.setattr(store, "atomic", delayed)
    with pytest.raises(IdentityDenied):
        if operation == "read":
            query.context(*credentials)
        elif operation == "commit":
            gateway.commit(*credentials, proposal.proposal_id, uuid4())
        else:
            gateway.preview(*credentials, student)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.student")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal")).scalar_one() == (2 if proposal else 1)
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE outcome='denied'")).scalar_one() == 1
