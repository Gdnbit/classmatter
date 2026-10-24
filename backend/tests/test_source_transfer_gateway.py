"""Disposable PG source freeze only; no target import or real instance."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.roster import CommandRejected, BusinessGateway, QueryGateway
from class_os.application.source_transfer import SourceTransferGateway, SourceTransferQueryGateway
from class_os.domain.source_transfer import SealConversationSource
from class_os.domain.conversation_control import ClearConversation
from class_os.domain.roster import CreateStudent, ChangeClass
from class_os.infrastructure.roster import PostgresBusinessStore
from class_os.infrastructure.source_transfer import ProtectedSourceTransfer, FILE_NAME, TransferUnavailable
from class_os.infrastructure.source_transfer_store import SourceTransferStore
from class_os.infrastructure.persistence.database import Database
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions, FILE_NAME as RESTRICTIONS_FILE
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from test_model_secrets import fixture_codec
from class_os.infrastructure.local_runtime import protect
from test_conversation_exit_gateway import world, control, storage, roster, identity, exported
from test_conversation_control import approve


@pytest.fixture
def transfer(world):
    store = SourceTransferStore(world[2].database, world[3])
    gateway = SourceTransferGateway(world[0].identity, store, clock=world[0].clock)
    # No dispatcher exists yet; represent a never-dispatched cancelled fixture.
    with world[4].transaction() as connection:
        connection.execute(text("UPDATE class_os.conversation_run SET state='cancelled',version=2,ended_at=created_at"))
    artifact = exported(world)
    command = SealConversationSource(uuid4(), artifact.export_id, artifact.package_hash, uuid4(), uuid4(), "d" * 64)
    return world, gateway, store, command, artifact


def approved(data):
    world, gateway, *_ = data
    proposal = gateway.preview(*world[6], data[3])
    assert proposal.risk == "X"
    nonce = gateway.approve(*world[6], proposal.proposal_id, proposal.payload_hash)
    return proposal, nonce


def commit(data, prepared, key=None):
    world, gateway, *_ = data
    proposal, nonce = prepared
    return gateway.commit(*world[6], proposal.proposal_id, key or uuid4(), nonce)


def ordinary_denied(data):
    world, _, _, _, artifact = data
    values = world[5]
    operations = [
        lambda: world[1].roster(*world[6], values["class"], values["term"]),
        lambda: world[1].conversation_history(*world[6], values["class"], values["term"], values["thread"]),
        lambda: world[1].conversation_exit_summary(*world[6]),
        lambda: world[1].conversation_exit_download(*world[6], artifact.export_id),
        lambda: world[0].preview(*world[6], CreateStudent(uuid4(), values["class"], values["term"], 1, "合成不应新增")),
        lambda: world[0].preview(*world[6], ClearConversation(values["thread"], values["class"], values["term"], 1)),
    ]
    for operation in operations:
        with pytest.raises(CommandRejected):
            operation()


@pytest.mark.db
def test_approved_source_freeze_blocks_normal_boundaries_and_replays_receipt(transfer):
    world, gateway, store, command, artifact = transfer
    normal = world[0].preview(*world[6], ChangeClass("class.update", world[5]["class"], world[5]["term"], 1, "合成不可更名班级"))
    normal_approval = world[0].approve(*world[6], normal.proposal_id, normal.payload_hash)
    prepared = approved(transfer)
    key = uuid4()
    with pytest.raises(CommandRejected):
        gateway.commit(*world[6], prepared[0].proposal_id, key)
    receipt = commit(transfer, prepared, key)
    assert receipt.resource_id == command.attempt_id
    assert commit(transfer, prepared, key) == receipt
    query = SourceTransferQueryGateway(gateway.identity, store, clock=gateway.clock)
    assert query.command_status(*world[6], prepared[0].proposal_id, key).receipt == receipt
    fence = ProtectedSourceTransfer(world[3]).read()
    with world[4].transaction(read_only=True) as connection:
        row = connection.execute(text("SELECT transfer_id,transfer_hash,transfer_at FROM class_os.conversation_control")).one()
        assert row == (command.attempt_id, ProtectedSourceTransfer(world[3]).digest(fence), fence.created_at)
        assert connection.execute(text("SELECT count(*) FROM class_os.student")).scalar_one() == 1
        assert connection.execute(text("SELECT body FROM class_os.conversation_message")).scalar_one() == "合成耐久导出原文"
    ordinary_denied(transfer)
    # Generic D1 composition cannot bypass the lifecycle gate with an R1 store.
    unsafe = PostgresBusinessStore(world[2].database)
    with pytest.raises(CommandRejected):
        QueryGateway(world[0].identity, unsafe, clock=world[0].clock).roster(*world[6], world[5]["class"], world[5]["term"])
    mislabeled = Database(world[2].database.engine.url)
    try:
        wrong = PostgresBusinessStore(mislabeled)
        with pytest.raises(CommandRejected):
            QueryGateway(world[0].identity, wrong, clock=world[0].clock).roster(*world[6], world[5]["class"], world[5]["term"])
        with pytest.raises(CommandRejected):
            BusinessGateway(world[0].identity, wrong, clock=world[0].clock).commit(*world[6], normal.proposal_id, uuid4(), normal_approval)
    finally:
        mislabeled.close()
    # An ordinary Gateway cannot borrow the privileged source retry path.
    with pytest.raises(CommandRejected):
        BusinessGateway(world[0].identity, store, clock=world[0].clock).commit(*world[6], prepared[0].proposal_id, key, prepared[1])


@pytest.mark.db
def test_file_first_audit_rollback_keeps_source_frozen_and_same_attempt_can_finish(transfer, monkeypatch):
    world, gateway, store, command, _ = transfer
    prepared, key = approved(transfer), uuid4()
    with monkeypatch.context() as patch:
        patch.setattr(store, "audit", lambda *args: None)
        with pytest.raises(AuditUnavailable):
            commit(transfer, prepared, key)
    assert ProtectedSourceTransfer(world[3]).read().command == command
    with world[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT transfer_id FROM class_os.conversation_control")).scalar_one() is None
    ordinary_denied(transfer)
    with pytest.raises(CommandRejected):
        gateway.preview(*world[6], replace(command, attempt_id=uuid4()))
    receipt = commit(transfer, prepared, key)
    assert receipt.resource_id == command.attempt_id
    ordinary_denied(transfer)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["missing", "corrupt", "partial-db-rollback"])
def test_lost_or_inconsistent_evidence_never_reopens_source(transfer, fault):
    world = transfer[0]
    commit(transfer, approved(transfer))
    path = world[3].root / FILE_NAME
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"synthetic-corrupt")
    else:
        with world[4].transaction() as connection:
            connection.execute(text("UPDATE class_os.conversation_control SET transfer_id=NULL,transfer_hash=NULL,transfer_at=NULL"))
    ordinary_denied(transfer)


@pytest.mark.db
def test_wrong_root_cannot_hide_file_first_fence_or_replay_old_approval(transfer, monkeypatch, tmp_path):
    world, gateway, store, *_ = transfer
    normal = world[0].preview(*world[6], ChangeClass("class.update", world[5]["class"], world[5]["term"], 1, "合成不可更名班级"))
    normal_approval = world[0].approve(*world[6], normal.proposal_id, normal.payload_hash)
    prepared = approved(transfer)
    with monkeypatch.context() as patch:
        patch.setattr(store, "audit", lambda *args: None)
        with pytest.raises(AuditUnavailable):
            commit(transfer, prepared)
    wrong_root = tmp_path / "wrong-root"
    wrong_root.mkdir()
    wrong = ConversationBusinessStore(world[2].database,
        ProtectedConversationRestrictions(wrong_root, world[5]["workspace"], codec=fixture_codec))
    with pytest.raises(CommandRejected):
        QueryGateway(world[0].identity, wrong, clock=world[0].clock).roster(*world[6], world[5]["class"], world[5]["term"])
    with pytest.raises(CommandRejected):
        BusinessGateway(world[0].identity, wrong, clock=world[0].clock).commit(*world[6], normal.proposal_id, uuid4(), normal_approval)
    ordinary_denied(transfer)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["wrong-package", "same-workspace", "same-owner", "same-root", "active-run", "stale-business", "old-auth"])
def test_invalid_transfer_refuses_before_publishing_fence(transfer, fault):
    world, gateway, _, command, _ = transfer
    if fault == "wrong-package":
        command = replace(command, package_hash="0" * 64)
    elif fault == "same-workspace":
        command = replace(command, target_workspace_id=world[5]["workspace"])
    elif fault == "same-owner":
        command = replace(command, target_owner_id=world[5]["owner"])
    elif fault == "same-root":
        command = replace(command, target_binding=world[3]._binding(world[3]._root()))
    elif fault == "old-auth":
        world[7][0] += timedelta(minutes=5, seconds=1)
    else:
        with world[4].transaction() as connection:
            if fault == "active-run":
                connection.execute(text("UPDATE class_os.conversation_run SET state='queued',ended_at=NULL,version=1"))
            else:
                connection.execute(text("UPDATE class_os.student SET name='合成已变化的学生',version=version+1"))
    with pytest.raises(CommandRejected):
        gateway.preview(*world[6], command)
    assert ProtectedSourceTransfer(world[3]).present() is False


@pytest.mark.db
def test_concurrent_same_key_seal_has_one_fence_and_receipt(transfer):
    world = transfer[0]
    prepared, key = approved(transfer), uuid4()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: commit(transfer, prepared, key), range(2)))
    assert results[0] == results[1]
    assert ProtectedSourceTransfer(world[3]).read().command == transfer[3]


@pytest.mark.db
def test_prior_clear_invalidates_source_export_and_no_fence_is_written(transfer):
    world = transfer[0]
    prepared = approved(transfer)
    command = ClearConversation(world[5]["thread"], world[5]["class"], world[5]["term"], 1)
    proposal = world[0].preview(*world[6], command)
    nonce = world[0].approve(*world[6], proposal.proposal_id, proposal.payload_hash)
    world[0].commit(*world[6], proposal.proposal_id, uuid4(), nonce)
    with pytest.raises(CommandRejected):
        commit(transfer, prepared)
    assert ProtectedSourceTransfer(world[3]).present() is False


@pytest.mark.db
def test_simultaneous_clear_and_seal_have_exactly_one_committed_outcome(transfer):
    world = transfer[0]
    seal_prepared = approved(transfer)
    proposal = world[0].preview(*world[6], ClearConversation(world[5]["thread"], world[5]["class"], world[5]["term"], 1))
    nonce = world[0].approve(*world[6], proposal.proposal_id, proposal.payload_hash)
    def run(which):
        try:
            result = commit(transfer, seal_prepared) if which == "seal" else world[0].commit(*world[6], proposal.proposal_id, uuid4(), nonce)
            return which, result
        except CommandRejected:
            return which, None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = dict(executor.map(run, ("clear", "seal")))
    assert sum(value is not None for value in results.values()) == 1
    if results["seal"] is not None:
        ordinary_denied(transfer)
    else:
        assert world[3].read().head.epoch == 1 and not ProtectedSourceTransfer(world[3]).present()


@pytest.mark.db
def test_sql_failure_after_file_freezes_without_false_receipt(transfer, monkeypatch):
    from class_os.infrastructure.source_transfer_store import SourceTransferTransaction
    prepared = approved(transfer)
    original = SourceTransferTransaction._mutate
    def fail(tx, statement, values, **options):
        if "transfer_id=:attempt" in str(statement):
            raise RuntimeError("Synthetic lost SQL mutation")
        return original(tx, statement, values, **options)
    with monkeypatch.context() as patch:
        patch.setattr(SourceTransferTransaction, "_mutate", fail)
        with pytest.raises(RuntimeError, match="Synthetic lost SQL mutation"):
            commit(transfer, prepared)
    assert ProtectedSourceTransfer(transfer[0][3]).present()
    ordinary_denied(transfer)
    assert commit(transfer, prepared).resource_id == transfer[3].attempt_id


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI and PostgreSQL source seal")
def test_actual_dpapi_and_pg_source_fence(transfer):
    world = transfer[0]
    path = world[3].root / RESTRICTIONS_FILE
    path.write_bytes(protect(fixture_codec(path.read_bytes(), decrypt=True)))
    actual = ProtectedConversationRestrictions(world[3].root, world[5]["workspace"])
    store = SourceTransferStore(world[2].database, actual)
    gateway = SourceTransferGateway(world[0].identity, store, clock=world[0].clock)
    changed = (world, gateway, store, transfer[3], transfer[4])
    assert commit(changed, approved(changed)).resource_id == transfer[3].attempt_id
    assert ProtectedSourceTransfer(actual).read().command == transfer[3]
    assert b'"root_binding"' not in (actual.root / FILE_NAME).read_bytes()
