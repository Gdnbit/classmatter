from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.roster import BusinessGateway, QueryGateway, CommandRejected
from class_os.domain.roster import CreateClass, CreateStudent
from class_os.infrastructure.roster import PostgresBusinessStore
from class_os.infrastructure.persistence.database import Database
from test_identity import identity, setup, CLIENT, PASSWORD
from class_os.application.identity import IdentityDenied


@pytest.fixture
def roster(identity, database_urls):
    boundary, owner, clock = identity
    auth = setup(boundary)
    store = PostgresBusinessStore(Database(database_urls["runtime"]))
    gateway = BusinessGateway(boundary, store, clock=lambda: clock[0])
    query = QueryGateway(boundary, store, clock=lambda: clock[0])
    credentials = (auth.token, CLIENT, auth.csrf, auth.subject.workspace_id)
    try:
        yield gateway, query, store, credentials, boundary, owner, clock
    finally:
        store.database.close()


def class_command():
    return CreateClass(uuid4(), uuid4(), "合成七一班", "合成第一学期", date(2026, 9, 1), date(2027, 1, 30))


def create_class(gateway, credentials):
    command = class_command()
    proposal = gateway.preview(*credentials, command)
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    receipt = gateway.commit(*credentials, proposal.proposal_id, uuid4(), approval)
    return command, receipt


@pytest.mark.db
def test_w2_class_then_w1_student_share_audited_query_world(roster):
    gateway, query, _, credentials, _, owner, _ = roster
    command, receipt = create_class(gateway, credentials)
    assert receipt.resource_id == command.class_id and receipt.version == 1
    student = CreateStudent(uuid4(), command.class_id, command.term_id, 1, "合成学生甲")
    preview = gateway.preview(*credentials, student)
    assert preview.risk == "W1"
    result = gateway.commit(*credentials, preview.proposal_id, uuid4())
    assert result.resource_id == student.student_id
    listed = query.roster(*credentials, command.class_id, command.term_id)
    assert [(item.student_id, item.name) for item in listed] == [(student.student_id, "合成学生甲")]
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='roster.list'")).scalar_one() == 1
        row = connection.execute(text("SELECT proposal_id,payload_hash,receipt_id,resource_id,resource_version FROM class_os.business_audit WHERE receipt_id=:id"), {"id": receipt.receipt_id}).one()
        assert row.proposal_id and len(row.payload_hash) == 64
        assert row.resource_id == command.class_id and row.resource_version == 1


@pytest.mark.db
def test_w2_cannot_commit_without_private_bound_approval(roster):
    gateway, _, _, credentials, boundary, _, _ = roster
    proposal = gateway.preview(*credentials, class_command())
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, proposal.proposal_id, uuid4())
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    second = boundary.login(PASSWORD, CLIENT)
    other = (second.token, CLIENT, second.csrf, second.subject.workspace_id)
    with pytest.raises(CommandRejected):
        gateway.commit(*other, proposal.proposal_id, uuid4(), approval)
    gateway.commit(*credentials, proposal.proposal_id, uuid4(), approval)
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, proposal.proposal_id, uuid4(), approval)


@pytest.mark.db
def test_identical_concurrent_retries_return_one_receipt(roster):
    gateway, _, _, credentials, _, owner, _ = roster
    proposal = gateway.preview(*credentials, class_command())
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: gateway.commit(*credentials, proposal.proposal_id, key, approval), range(2)))
    assert results[0] == results[1]
    with owner.transaction(read_only=True) as connection:
        for table in ("school_class", "academic_term", "command_receipt"):
            assert connection.execute(text(f"SELECT count(*) FROM class_os.{table}")).scalar_one() == 1


@pytest.mark.db
def test_business_audit_failure_rolls_back_entities_receipt_and_approval_consumption(roster, monkeypatch):
    gateway, _, store, credentials, _, owner, _ = roster
    proposal = gateway.preview(*credentials, class_command())
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    key = uuid4()
    original = store.audit
    monkeypatch.setattr(store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError, match="audit unavailable"):
        gateway.commit(*credentials, proposal.proposal_id, key, approval)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.school_class")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.command_receipt")).scalar_one() == 0
        assert connection.execute(text("SELECT consumed_at FROM class_os.approval_receipt")).scalar_one() is None
    monkeypatch.setattr(store, "audit", original)
    gateway.commit(*credentials, proposal.proposal_id, key, approval)


@pytest.mark.db
def test_query_audit_failure_releases_no_projection(roster, monkeypatch):
    gateway, query, store, credentials, _, _, _ = roster
    command, _ = create_class(gateway, credentials)
    monkeypatch.setattr(store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError, match="audit unavailable"):
        query.roster(*credentials, command.class_id, command.term_id)


@pytest.mark.db
def test_expired_foreign_scope_and_changed_hash_fail_closed(roster):
    gateway, query, _, credentials, _, _, clock = roster
    command = class_command()
    proposal = gateway.preview(*credentials, command)
    with pytest.raises(CommandRejected):
        gateway.approve(*credentials, proposal.proposal_id, "0" * 64)
    with pytest.raises(IdentityDenied):
        gateway.preview(*credentials[:3], uuid4(), command)
    with pytest.raises(CommandRejected):
        query.roster(*credentials, uuid4(), uuid4())
    clock[0] += timedelta(minutes=10)
    with pytest.raises(CommandRejected):
        gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)


@pytest.mark.db
def test_rejected_proposal_and_conflicting_idempotency_key_cannot_be_reused(roster):
    gateway, _, _, credentials, _, _, _ = roster
    proposal = gateway.preview(*credentials, class_command())
    gateway.reject(*credentials, proposal.proposal_id)
    with pytest.raises(CommandRejected):
        gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    command = class_command()
    valid = gateway.preview(*credentials, command)
    proof = gateway.approve(*credentials, valid.proposal_id, valid.payload_hash)
    key = uuid4()
    gateway.commit(*credentials, valid.proposal_id, key, proof)
    other = gateway.preview(*credentials, CreateStudent(uuid4(), command.class_id, command.term_id, 1, "合成另一位"))
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, other.proposal_id, key)


@pytest.mark.db
def test_invalid_class_version_and_forged_risk_do_not_bypass_revalidation(roster):
    gateway, _, _, credentials, _, owner, _ = roster
    proposal = gateway.preview(*credentials, class_command())
    # Privileged fault injection, not a supported application write adapter.
    with owner.transaction() as connection:
        connection.execute(text("UPDATE class_os.command_proposal SET risk='W1' WHERE proposal_id=:p"), {"p": proposal.proposal_id})
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, proposal.proposal_id, uuid4())
    proof = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    receipt = gateway.commit(*credentials, proposal.proposal_id, uuid4(), proof)
    with owner.transaction(read_only=True) as connection:
        term_id = connection.execute(text("SELECT term_id FROM class_os.school_class WHERE class_id=:c"), {"c": receipt.resource_id}).scalar_one()
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, CreateStudent(uuid4(), receipt.resource_id, term_id, 2, "合成甲"))


@pytest.mark.db
def test_business_audit_is_append_only_and_identity_cannot_read_roster(roster):
    gateway, _, store, credentials, boundary, _, _ = roster
    create_class(gateway, credentials)
    for database, statement in [(store.database, "DELETE FROM class_os.business_audit"),
                                (store.database, "UPDATE class_os.command_receipt SET resource_version=2"),
                                (boundary.store.database, "SELECT * FROM class_os.student")]:
        with pytest.raises(ProgrammingError) as denied, database.transaction() as connection:
            connection.execute(text(statement))
        assert denied.value.orig.sqlstate == "42501"
