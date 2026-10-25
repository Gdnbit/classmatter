"""Two real owned PG databases: committed stage -> human source retirement."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from threading import Barrier
from datetime import timedelta
import os
from uuid import uuid4

import pytest
import psycopg
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.identity import IdentityDenied
from class_os.application.roster import CommandRejected, QueryGateway
from class_os.application.source_retirement import AuthorizedTargetReader, SourceRetirementGateway, SourceRetirementQueryGateway
from class_os.domain.source_retirement import RetireConversationSource
from class_os.infrastructure.source_retirement import ProtectedSourceRetirement, FILE_NAME
from class_os.infrastructure.source_retirement_store import SourceRetirementStore
from class_os.infrastructure.source_retirement_store import SourceRetirementTransaction
from class_os.infrastructure.source_transfer import FILE_NAME as SEAL_FILE
from class_os.infrastructure.target_import import FILE_NAME as TARGET_FILE
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from class_os.infrastructure.persistence.database import Database
from class_os.infrastructure.operator_backup import SyntheticBackup
from test_target_import_gateway import target, prepare, approved, commit, ordinary_denied
from test_conversation_exit_gateway import prepare as prepare_world, control, storage, roster, identity
from test_model_secrets import fixture_codec


@pytest.fixture
def world(control, request):
    return prepare_world(control, actual=getattr(request, "param", False))


def retirement(world, data):
    stage = data.query.committed_stage(*data.credentials, data.command.attempt_id)
    reader = AuthorizedTargetReader(data.query, data.credentials, data.command.attempt_id)
    store = SourceRetirementStore(world[2].database, world[3], reader)
    gateway = SourceRetirementGateway(world[0].identity, store, clock=world[0].clock)
    query = SourceRetirementQueryGateway(gateway.identity, store, clock=gateway.clock)
    command = RetireConversationSource(data.command.attempt_id, stage.snapshot_hash)
    return store, gateway, query, command, stage


def approve_retirement(world, gateway, command):
    proposal = gateway.preview(*world[6], command)
    assert proposal.risk == "X"
    nonce = gateway.approve(*world[6], proposal.proposal_id, proposal.payload_hash)
    return proposal, nonce


def commit_retirement(world, gateway, prepared, key=None):
    proposal, nonce = prepared
    return gateway.commit(*world[6], proposal.proposal_id, key or uuid4(), nonce)


@pytest.mark.db
def test_real_import_retirement_replay_reopen_and_checkpoint(world, target, tmp_path):
    data = prepare(world, target)
    imported = commit(data, approved(data))
    store, gateway, query, command, stage = retirement(world, data)
    assert stage.receipt_id == imported.receipt_id
    prepared, key = approve_retirement(world, gateway, command), uuid4()
    with pytest.raises(CommandRejected):
        gateway.commit(*world[6], prepared[0].proposal_id, key)
    receipt = commit_retirement(world, gateway, prepared, key)
    assert receipt.version == 2 and receipt.resource_id == command.attempt_id
    assert commit_retirement(world, gateway, prepared, key) == receipt
    assert query.command_status(*world[6], prepared[0].proposal_id, key).receipt == receipt
    result = query.committed_retirement(*world[6], command.attempt_id)
    assert result.receipt_id == receipt.receipt_id and result.fence.stage == stage
    assert data.query.committed_stage(*data.credentials, command.attempt_id) == stage
    with pytest.raises(CommandRejected):
        data.source.committed_source(*world[6], command.attempt_id)
    with pytest.raises(CommandRejected):
        gateway.preview(*world[6], command)
    with world[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() == "0022"
    assert data.artifact.bundle["source_revision"] == "0021"  # Fixed v4 projection, not DB migration authority.
    ordinary_denied(data)
    with pytest.raises(CommandRejected):
        world[1].roster(*world[6], world[5]["class"], world[5]["term"])
    # Reopen actual repositories; no cached observation becomes authority.
    reopened = Database(world[2].database.engine.url, profile="conversation-d1")
    try:
        new_query = SourceRetirementQueryGateway(gateway.identity, SourceRetirementStore(reopened, world[3]), clock=gateway.clock)
        assert new_query.committed_retirement(*world[6], command.attempt_id) == result
    finally:
        reopened.close()
    # SQL checkpoint includes the existing command/receipt/audit evidence,
    # but does not copy the external retirement file or grant activation.
    class Runtime:
        root = world[3].root
        def configuration(self):
            binaries = target.binaries / "bin" if (target.binaries / "bin").is_dir() else target.binaries
            return {"profile": "class-os-owned-synthetic-v1", "pg_bin": str(binaries),
                    "port": target.cluster["port"], "database": world[4].engine.url.database}
        def password(self, role):
            assert role == "migrator"
            return ""
        def database(self, role):
            assert role == "migrator"
            return Database(world[4].engine.url, migration=True, profile="conversation-d1")
        @contextmanager
        def admin(self):
            with psycopg.connect(**target.cluster, autocommit=True) as connection:
                yield connection
    backup = SyntheticBackup(Runtime(), codec=fixture_codec, profile="conversation-d1")
    artifact = backup.create()
    checked = backup.check(artifact)
    assert checked["activation_allowed"] is False and checked["table_count"] == 30


@pytest.mark.db
def test_uncommitted_target_and_invalid_metadata_never_retire(world, target):
    data = prepare(world, target)
    with pytest.raises(CommandRejected):
        data.query.committed_stage(*data.credentials, data.command.attempt_id)
    assert not ProtectedSourceRetirement(world[3]).present()
    commit(data, approved(data))
    store, gateway, query, command, _ = retirement(world, data)
    for invalid in (replace(command, attempt_id=uuid4()), replace(command, expected_stage_hash="0" * 64)):
        with pytest.raises(CommandRejected):
            gateway.preview(*world[6], invalid)
    with pytest.raises(CommandRejected):
        query.committed_retirement(*world[6], command.attempt_id)
    assert not ProtectedSourceRetirement(world[3]).present()
    with pytest.raises(ValueError):
        SourceRetirementStore(world[2].database, world[3], {})
    with pytest.raises(ValueError):
        AuthorizedTargetReader({}, data.credentials, data.command.attempt_id)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["missing", "corrupt", "row", "source-audit"])
def test_current_target_evidence_is_required_before_retirement(world, target, fault):
    data = prepare(world, target)
    commit(data, approved(data))
    store, gateway, _, command, _ = retirement(world, data)
    path = data.restrictions.root / TARGET_FILE
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"synthetic-corrupt")
    else:
        with data.dbs["migrator"].transaction() as connection:
            statement = "UPDATE class_os.student SET name='合成篡改'" if fault == "row" else "UPDATE class_os.conversation_source_audit SET purpose='unknown'"
            connection.execute(text(statement))
    with pytest.raises(CommandRejected):
        gateway.preview(*world[6], command)
    assert not ProtectedSourceRetirement(world[3]).present()


@pytest.mark.db
def test_identity_revocation_and_old_auth_refuse_without_file(world, target):
    data = prepare(world, target)
    commit(data, approved(data))
    _, gateway, _, command, _ = retirement(world, data)
    data.identity.logout(*data.credentials[:3])
    with pytest.raises(IdentityDenied):
        gateway.preview(*world[6], command)
    assert not ProtectedSourceRetirement(world[3]).present()


@pytest.mark.db
def test_old_recent_auth_refuses_without_file(world, target):
    data = prepare(world, target)
    commit(data, approved(data))
    _, gateway, _, command, _ = retirement(world, data)
    data.clock[0] += timedelta(minutes=6)
    with pytest.raises(CommandRejected):
        gateway.preview(*world[6], command)
    assert not ProtectedSourceRetirement(world[3]).present()


@pytest.mark.db
def test_file_first_audit_rollback_same_attempt_retry(world, target, monkeypatch):
    data = prepare(world, target)
    commit(data, approved(data))
    store, gateway, query, command, _ = retirement(world, data)
    prepared = approve_retirement(world, gateway, command)
    with monkeypatch.context() as patch:
        patch.setattr(store, "audit", lambda *args: None)
        with pytest.raises(AuditUnavailable):
            commit_retirement(world, gateway, prepared)
    assert ProtectedSourceRetirement(world[3]).present()
    with pytest.raises(CommandRejected):
        data.source.committed_source(*world[6], command.attempt_id)
    with pytest.raises(CommandRejected):
        query.committed_retirement(*world[6], command.attempt_id)
    with world[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.command_receipt r JOIN class_os.command_proposal p USING(proposal_id) WHERE p.command_type='conversation.transfer.retire'")).scalar_one() == 0
    receipt = commit_retirement(world, gateway, prepared)
    assert query.committed_retirement(*world[6], command.attempt_id).receipt_id == receipt.receipt_id


@pytest.mark.db
def test_file_first_sql_failure_never_commits_and_retries_original(world, target, monkeypatch):
    data = prepare(world, target)
    commit(data, approved(data))
    _, gateway, query, command, _ = retirement(world, data)
    prepared, key = approve_retirement(world, gateway, command), uuid4()
    with monkeypatch.context() as patch:
        patch.setattr(SourceRetirementTransaction, "finish", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic SQL rollback")))
        with pytest.raises(RuntimeError, match="SQL rollback"):
            commit_retirement(world, gateway, prepared, key)
    assert ProtectedSourceRetirement(world[3]).present()
    with pytest.raises(CommandRejected):
        query.committed_retirement(*world[6], command.attempt_id)
    receipt = commit_retirement(world, gateway, prepared, key)
    assert query.committed_retirement(*world[6], command.attempt_id).receipt_id == receipt.receipt_id


@pytest.mark.db
def test_target_file_only_cannot_become_a_committed_stage(world, target, monkeypatch):
    data = prepare(world, target)
    prepared = approved(data)
    with monkeypatch.context() as patch:
        patch.setattr(data.store, "audit", lambda *args: None)
        with pytest.raises(AuditUnavailable):
            commit(data, prepared)
    assert (data.restrictions.root / TARGET_FILE).exists()
    with pytest.raises(CommandRejected):
        data.query.committed_stage(*data.credentials, data.command.attempt_id)
    from class_os.application.source_transfer import SourceTransferQueryGateway
    source = data.source.committed_source(*world[6], data.command.attempt_id)
    assert source.fence_hash == data.command.source_fence_hash
    reader = AuthorizedTargetReader(data.query, data.credentials, data.command.attempt_id)
    store = SourceRetirementStore(world[2].database, world[3], reader)
    gateway = SourceRetirementGateway(world[0].identity, store, clock=world[0].clock)
    with pytest.raises(CommandRejected):
        gateway.preview(*world[6], RetireConversationSource(data.command.attempt_id, "0" * 64))
    assert not ProtectedSourceRetirement(world[3]).present()


@pytest.mark.db
@pytest.mark.parametrize("fault", ["missing", "corrupt", "directory", "receipt"])
def test_uncertain_committed_retirement_refuses_proof_without_thaw(world, target, fault):
    data = prepare(world, target)
    commit(data, approved(data))
    _, gateway, query, command, _ = retirement(world, data)
    commit_retirement(world, gateway, approve_retirement(world, gateway, command))
    path = world[3].root / FILE_NAME
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"synthetic-corrupt")
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    else:
        with world[4].transaction() as connection:
            connection.execute(text("DELETE FROM class_os.command_receipt WHERE resource_id=:id AND resource_version=2"), {"id": command.attempt_id})
    with pytest.raises(CommandRejected):
        query.committed_retirement(*world[6], command.attempt_id)
    with pytest.raises(CommandRejected):
        gateway.preview(*world[6], command)
    with pytest.raises(CommandRejected):
        world[1].context(*world[6])
    ordinary_denied(data)


@pytest.mark.db
def test_concurrent_retirement_is_single_receipt(world, target):
    data = prepare(world, target)
    commit(data, approved(data))
    _, gateway, query, command, _ = retirement(world, data)
    prepared, key = approve_retirement(world, gateway, command), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: commit_retirement(world, gateway, prepared, key), range(2)))
    assert values[0] == values[1] and query.committed_retirement(*world[6], command.attempt_id).receipt_id == values[0].receipt_id


@pytest.mark.db
def test_committed_target_preview_never_reenters_source(world, target, monkeypatch):
    data = prepare(world, target)
    commit(data, approved(data))
    def forbidden():
        raise AssertionError("Committed target must not acquire source again")
    monkeypatch.setattr(data.store.source, "current", forbidden)
    with pytest.raises(CommandRejected):
        data.gateway.preview(*data.credentials, data.command)


@pytest.mark.db
def test_target_duplicate_preview_and_source_retirement_finish_without_false_success(world, target):
    data = prepare(world, target)
    imported = commit(data, approved(data))
    _, gateway, query, command, _ = retirement(world, data)
    prepared, barrier = approve_retirement(world, gateway, command), Barrier(2)
    def duplicate():
        barrier.wait(timeout=10)
        with pytest.raises(CommandRejected):
            data.gateway.preview(*data.credentials, data.command)
    def retire():
        barrier.wait(timeout=10)
        return commit_retirement(world, gateway, prepared)
    with ThreadPoolExecutor(max_workers=2) as pool:
        left, right = pool.submit(duplicate), pool.submit(retire)
        assert left.result(timeout=20) is None
        receipt = right.result(timeout=20)
    assert query.committed_retirement(*world[6], command.attempt_id).receipt_id == receipt.receipt_id
    assert data.query.committed_stage(*data.credentials, command.attempt_id).receipt_id == imported.receipt_id
    ordinary_denied(data)


@pytest.mark.db
def test_retirement_file_alone_never_thaws_source_after_sql_and_seal_loss(world, target):
    data = prepare(world, target)
    commit(data, approved(data))
    _, gateway, query, command, _ = retirement(world, data)
    commit_retirement(world, gateway, approve_retirement(world, gateway, command))
    # Simulate partial source SQL/file rollback, retaining external retirement.
    (world[3].root / SEAL_FILE).unlink()
    with world[4].transaction() as connection:
        connection.execute(text("UPDATE class_os.conversation_control SET transfer_id=NULL,transfer_hash=NULL,transfer_at=NULL"))
    for store in (world[2], ConversationBusinessStore(world[2].database, world[3])):
        with pytest.raises(CommandRejected):
            QueryGateway(gateway.identity, store, clock=gateway.clock).context(*world[6])
    with pytest.raises(CommandRejected):
        query.committed_retirement(*world[6], command.attempt_id)
    # Even the specialized source-seal Gateway cannot open another handoff
    # using an old still-unexpired artifact after partial rollback.
    from class_os.application.source_transfer import SourceTransferGateway
    from class_os.infrastructure.source_transfer_store import SourceTransferStore
    from class_os.domain.source_transfer import SealConversationSource
    reseal = SourceTransferGateway(gateway.identity, SourceTransferStore(world[2].database, world[3]), clock=gateway.clock)
    changed = SealConversationSource(uuid4(), data.artifact.export_id, data.artifact.package_hash, uuid4(), uuid4(), "b" * 64)
    with pytest.raises(CommandRejected):
        reseal.preview(*world[6], changed)
    assert not (world[3].root / SEAL_FILE).exists()
    ordinary_denied(data)


@pytest.mark.db
@pytest.mark.parametrize("world,target", [(True, True)], indirect=True)
@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI target and source retirement")
def test_actual_dpapi_and_pg_retirement(world, target):
    data = prepare(world, target)
    commit(data, approved(data))
    _, gateway, query, command, _ = retirement(world, data)
    receipt = commit_retirement(world, gateway, approve_retirement(world, gateway, command))
    assert query.committed_retirement(*world[6], command.attempt_id).receipt_id == receipt.receipt_id
    assert b"snapshot_hash" not in (world[3].root / FILE_NAME).read_bytes()
