"""Owned synthetic PostgreSQL: dispatch, cancellation, faults and recovery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.conversation_worker import ConversationWorkerGateway
from class_os.application.roster import CommandRejected
from class_os.domain.conversation_worker import ClaimRun
from class_os.infrastructure.recovery_admission_store import AdmissionTransaction
from class_os.domain.conversation_exit import CreateConversationExit
from class_os.domain.conversation_exit_v5 import validate_v5
from test_conversation_interaction_gateway import prepared, enqueue
from test_conversation_control import control, storage, roster, identity
from test_recovery_admission_gateway import world, target, ready, approve, submit, checkpoint


def queued(control):
    value = prepared(control)
    value.worker = ConversationWorkerGateway(value.gateway.identity, value.store, clock=lambda: control[7][0])
    value.key = uuid4()
    value.run_id = enqueue(value, value.key).receipt.resource_id
    return value


def claim(value):
    return value.worker.claim(value.auth, value.ids["class"], value.ids["term"], value.thread, value.key)


def status(value):
    return value.query.turn_status(*value.auth, value.ids["class"], value.ids["term"], value.thread, value.key)


@pytest.mark.db
def test_concurrent_claim_once_completion_reopen_and_metadata_only(control):
    value = queued(control)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(value), range(2)))
    ticket, = [item for item in results if item is not None]
    assert results.count(None) == 1 and ticket.run.version == 2
    result = value.worker.finish_run(value.auth, ticket, "completed", "合成未核实回复", duration_ms=12)
    assert result.receipt.version == 3 and status(value)["state"] == "completed"
    assert claim(value) is None
    history = value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread)
    assert history.history.messages[-1].content.text == "合成未核实回复"
    assert history.message_attributions[-1]["attribution"]["created_by"] is None
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal WHERE payload::text LIKE '%合成未核实回复%'")).scalar_one() == 0
        assert connection.execute(text("SELECT input_tokens FROM class_os.conversation_run")).scalar_one() is None
    with pytest.raises(CommandRejected):
        value.worker.finish_run(value.auth, ticket, "completed", "合成迟到回复")


@pytest.mark.db
@pytest.mark.parametrize("phase", ["claim", "finish"])
@pytest.mark.parametrize("fault", ["audit", "receipt"])
def test_transaction_failure_never_returns_dispatch_or_output(control, monkeypatch, phase, fault):
    value = queued(control)
    ticket = claim(value) if phase == "finish" else None
    with monkeypatch.context() as patch:
        if fault == "audit":
            patch.setattr(value.store, "audit", lambda *args: None)
            error = AuditUnavailable
        else:
            patch.setattr(AdmissionTransaction, "finish", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic receipt outage")))
            error = RuntimeError
        with pytest.raises(error):
            claim(value) if phase == "claim" else value.worker.finish_run(value.auth, ticket, "completed", "合成不可放行回复")
    assert status(value)["state"] == ("queued" if phase == "claim" else "running")
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE role='assistant'")).scalar_one() == 0
    if ticket:
        value.worker.finish_run(value.auth, ticket, "unknown")
    else:
        assert claim(value) is not None


@pytest.mark.db
@pytest.mark.parametrize("dispatched", [False, True])
def test_cancel_before_or_after_dispatch_cannot_complete(control, dispatched):
    value = queued(control)
    ticket = claim(value) if dispatched else None
    value.worker.cancel_run(value.auth, value.ids["class"], value.ids["term"], value.thread, value.run_id, 2 if dispatched else 1)
    assert status(value)["state"] == ("cancel_requested" if dispatched else "cancelled")
    if ticket:
        with pytest.raises(CommandRejected):
            value.worker.finish_run(value.auth, ticket, "completed", "合成已取消回复")
        value.worker.finish_run(value.auth, ticket, "cancelled")
    assert claim(value) is None
    assert status(value)["state"] == "cancelled"


@pytest.mark.db
@pytest.mark.parametrize("dispatched", [False, True])
def test_expiry_reconciles_without_restarting_provider(control, dispatched):
    value = queued(control)
    ticket = claim(value) if dispatched else None
    control[7][0] += timedelta(seconds=61)
    value.worker.reconcile_run(value.auth, value.ids["class"], value.ids["term"], value.thread, value.run_id)
    assert status(value)["state"] == ("interrupted" if dispatched else "cancelled")
    assert claim(value) is None
    if ticket:
        with pytest.raises(CommandRejected):
            value.worker.finish_run(value.auth, ticket, "completed", "合成过期回复")


@pytest.mark.db
def test_generic_command_cannot_mint_dispatch_and_forged_generation_rejected(control):
    value = queued(control)
    command = ClaimRun(value.thread, value.ids["class"], value.ids["term"], value.run_id, 1, uuid4(), control[7][0] + timedelta(minutes=1), "a" * 64)
    with pytest.raises(CommandRejected):
        value.worker.preview(*value.auth, command)
    ticket = claim(value)
    forged = replace(ticket, run=replace(ticket.run, generation=uuid4()))
    with pytest.raises(CommandRejected):
        value.worker.finish_run(value.auth, forged, "completed", "合成伪造代次")
    value.worker.finish_run(value.auth, ticket, "failed")


@pytest.mark.db
def test_original_enqueue_audit_required_before_dispatch(control):
    value = queued(control)
    with control[4].transaction() as connection:
        connection.execute(text("DELETE FROM class_os.business_audit WHERE action='command.commit' AND proposal_id IN (SELECT proposal_id FROM class_os.command_proposal WHERE command_type='conversation.enqueue')"))
    with pytest.raises(CommandRejected):
        claim(value)
    assert status(value)["state"] == "queued"


@pytest.mark.db
@pytest.mark.parametrize("fault", ["body", "claim-audit", "claim-payload"])
def test_finish_revalidates_input_and_original_claim_commit(control, fault):
    value = queued(control)
    ticket = claim(value)
    statements = {
        "body": "UPDATE class_os.conversation_message SET body='synthetic substituted input' WHERE role='user'",
        "claim-audit": "DELETE FROM class_os.business_audit WHERE action='command.commit' AND proposal_id IN (SELECT proposal_id FROM class_os.command_proposal WHERE command_type='conversation.run.claim')",
        "claim-payload": "UPDATE class_os.command_proposal SET payload=jsonb_set(payload,'{request_hash}',to_jsonb(repeat('b',64))) WHERE command_type='conversation.run.claim'",
    }
    with control[4].transaction() as connection:
        assert connection.execute(text(statements[fault])).rowcount == 1
    with pytest.raises(CommandRejected):
        value.worker.finish_run(value.auth, ticket, "completed", "合成旧输入结果")
    assert status(value)["state"] == "running"


@pytest.mark.db
def test_admitted_native_completion_clear_exit_and_real_checkpoint(world, target):
    recovered = ready(world, target)
    submit(recovered, approve(recovered))
    data, ids = recovered.data, world[5]
    worker = ConversationWorkerGateway(data.identity, recovered.store, clock=lambda: data.clock[0])
    from class_os.application.conversation_interaction import ConversationInteractionQuery
    from class_os.domain.conversation_control import ClearConversation
    query = ConversationInteractionQuery(data.identity, recovered.store, clock=lambda: data.clock[0])
    thread, key = uuid4(), uuid4()
    worker.create_conversation(*data.credentials, ids["class"], ids["term"], thread, uuid4(), "合成恢复后运行")
    worker.enqueue(*data.credentials, ids["class"], ids["term"], thread, key, "合成恢复后输入", "chat")
    ticket = worker.claim(data.credentials, ids["class"], ids["term"], thread, key)
    worker.finish_run(data.credentials, ticket, "completed", "合成恢复后未核实回复")
    history = query.conversation_history(*data.credentials, ids["class"], ids["term"], thread)
    assert history.history.messages[-1].content.text == "合成恢复后未核实回复"
    assert history.message_attributions[-1]["attribution"]["content_authority"] == "assistant-unverified"
    for command in (ClearConversation(thread, ids["class"], ids["term"], history.history.version),):
        proposal = worker.preview(*data.credentials, command)
        nonce = worker.approve(*data.credentials, proposal.proposal_id, proposal.payload_hash)
        worker.commit(*data.credentials, proposal.proposal_id, uuid4(), nonce)
    assert not query.conversation_history(*data.credentials, ids["class"], ids["term"], thread).history.messages
    summary = query.conversation_exit_summary(*data.credentials)
    command = CreateConversationExit(uuid4(), summary.snapshot_hash)
    proposal = worker.preview(*data.credentials, command)
    nonce = worker.approve(*data.credentials, proposal.proposal_id, proposal.payload_hash)
    worker.commit(*data.credentials, proposal.proposal_id, uuid4(), nonce)
    bundle = query.conversation_exit_download(*data.credentials, command.export_id).bundle
    assert validate_v5(bundle) and bundle["activation_allowed"] is False
    backup = checkpoint(recovered)
    checked = backup.check_current_restrictions(backup.create(), data.restrictions)
    assert checked["snapshot_integrity_verified"] and not checked["activation_allowed"]
