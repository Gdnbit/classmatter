"""Human-only BCG durable input on owned synthetic PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.roster import CommandRejected
from class_os.application.conversation_interaction import ConversationInteractionGateway, ConversationInteractionQuery
from class_os.domain.conversation_control import InitializeConversationControl, ClearConversation
from class_os.domain.conversation_interaction import CreateConversation, RenameConversation, ArchiveConversation
from class_os.infrastructure.recovery_admission_store import AdmissionStore, AdmissionTransaction
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from class_os.domain.conversation_exit import CreateConversationExit
from class_os.domain.conversation_exit_v6 import validate_v6
from test_conversation_control import control, storage, roster, identity, commit as control_commit
from test_recovery_admission_gateway import world, target, ready, approve as approve_admission, submit as submit_admission, checkpoint


def prepared(control):
    control_commit(control, InitializeConversationControl(uuid4()))
    store = AdmissionStore(control[2].database, control[3])
    gateway = ConversationInteractionGateway(control[0].identity, store, clock=lambda: control[7][0])
    query = ConversationInteractionQuery(control[0].identity, store, clock=lambda: control[7][0])
    value = SimpleNamespace(store=store, gateway=gateway, query=query, auth=control[6], ids=control[5], control=control, thread=uuid4())
    gateway.create_conversation(*value.auth, value.ids["class"], value.ids["term"], value.thread, uuid4(), "合成人工会话", value.ids["student"])
    return value


def apply(value, command):
    proposal = value.gateway.preview(*value.auth, command)
    assert proposal.risk == "W1"
    return value.gateway.commit(*value.auth, proposal.proposal_id, uuid4())


def enqueue(value, key=None, body="合成输入只存消息，不存提案正文"):
    return value.gateway.enqueue(*value.auth, value.ids["class"], value.ids["term"], value.thread, key or uuid4(), body, "chat")


@pytest.mark.db
def test_real_create_rename_archive_and_reopened_list(control):
    value = prepared(control)
    value.gateway.rename_conversation(*value.auth, value.ids["class"], value.ids["term"], value.thread, uuid4(), 1, "合成持久改名")
    apply(value, ArchiveConversation(value.thread, value.ids["class"], value.ids["term"], 2))
    reopened = ConversationInteractionQuery(value.gateway.identity, AdmissionStore(control[2].database, control[3]), clock=lambda: control[7][0])
    page = reopened.conversations(*value.auth, value.ids["class"], value.ids["term"])
    assert not page.truncated and len(page.items) == 1
    assert page.items[0]["title"] == "合成持久改名" and page.items[0]["status"] == "archived" and page.items[0]["version"] == 3
    assert page.items[0]["attribution"]["created_by"] == str(value.ids["owner"])
    with pytest.raises(CommandRejected):
        enqueue(value)


@pytest.mark.db
def test_real_concurrent_same_input_is_one_message_and_queued_run(control):
    value = prepared(control)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: enqueue(value, key), range(2)))
    assert results[0] == results[1] and results[0].status == "committed"
    history = value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread)
    assert history.history.version == 2 and len(history.history.messages) == 1
    assert history.history.messages[0].content.text == "合成输入只存消息，不存提案正文"
    status = value.query.turn_status(*value.auth, value.ids["class"], value.ids["term"], value.thread, key)
    assert status["state"] == "queued" and status["run_id"] == results[0].receipt.resource_id
    assert "generation" not in status  # Metadata is not a dispatch capability.
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_turn")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_run")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal WHERE command_type='conversation.enqueue'")).scalar_one() == 1
        payload = connection.execute(text("SELECT payload FROM class_os.command_proposal WHERE command_type='conversation.enqueue'")).scalar_one()
        assert "text" not in payload and "body" not in payload
        assert "合成输入" not in str(payload)
    with pytest.raises(CommandRejected):
        enqueue(value, key, "合成相同键不同原文")
    with pytest.raises(CommandRejected):
        enqueue(value)  # A queued run already owns this thread's slot.
    with pytest.raises(CommandRejected):
        apply(value, ArchiveConversation(value.thread, value.ids["class"], value.ids["term"], 2))


@pytest.mark.db
@pytest.mark.parametrize("fault", ["audit", "finish"])
def test_input_persistence_failure_has_no_partial_queue(control, monkeypatch, fault):
    value = prepared(control)
    key = uuid4()
    with monkeypatch.context() as patch:
        if fault == "audit":
            patch.setattr(value.store, "audit", lambda *args: None)
            error = AuditUnavailable
        else:
            patch.setattr(AdmissionTransaction, "finish", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic finish")))
            error = RuntimeError
        with pytest.raises(error):
            enqueue(value, key)
    with control[4].transaction(read_only=True) as connection:
        for table in ("conversation_turn", "conversation_message", "conversation_run"):
            assert connection.execute(text("SELECT count(*) FROM class_os." + table)).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal WHERE command_type='conversation.enqueue'")).scalar_one() == 0
    assert enqueue(value, key).status == "committed"


@pytest.mark.db
def test_clear_cancels_queued_input_without_proposal_body_copy(control):
    value = prepared(control)
    key = uuid4()
    enqueue(value, key)
    command = ClearConversation(value.thread, value.ids["class"], value.ids["term"], 2)
    proposal = value.gateway.preview(*value.auth, command)
    nonce = value.gateway.approve(*value.auth, proposal.proposal_id, proposal.payload_hash)
    value.gateway.commit(*value.auth, proposal.proposal_id, uuid4(), nonce)
    assert not value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread).history.messages
    assert value.query.turn_status(*value.auth, value.ids["class"], value.ids["term"], value.thread, key)["state"] == "cancelled"
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT body FROM class_os.conversation_message")).scalar_one() is None
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal WHERE payload::text LIKE '%合成输入%'")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal WHERE payload::text LIKE '%合成人工会话%'")).scalar_one() == 0
    with pytest.raises(CommandRejected):
        enqueue(value, key)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["body", "mode", "draft", "audit"])
def test_replay_checks_actual_saved_input_not_only_declared_hash(control, fault):
    value = prepared(control)
    key = uuid4()
    enqueue(value, key)
    statements = {
        "body": "UPDATE class_os.conversation_message SET body='synthetic substituted body' WHERE role='user'",
        "mode": "UPDATE class_os.conversation_turn SET mode='read'",
        "draft": "UPDATE class_os.conversation_turn SET draft_kind='record-note'",
        "audit": "DELETE FROM class_os.business_audit WHERE action='command.commit' AND proposal_id IN (SELECT proposal_id FROM class_os.command_proposal WHERE command_type='conversation.enqueue')",
    }
    with control[4].transaction() as connection:
        assert connection.execute(text(statements[fault])).rowcount == 1
    with pytest.raises(CommandRejected):
        enqueue(value, key)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["audit", "receipt-hash", "receipt-version", "command", "purpose"])
def test_title_replay_requires_original_complete_commit_evidence(control, fault):
    value = prepared(control)
    with control[4].transaction(read_only=True) as connection:
        key = connection.execute(text("SELECT idempotency_key FROM class_os.command_receipt WHERE resource_id=:thread"),
                                 {"thread": value.thread}).scalar_one()
    # A legitimate later rename does not invalidate the creation receipt.
    value.gateway.rename_conversation(*value.auth, value.ids["class"], value.ids["term"], value.thread, uuid4(), 1, "合成后续标题")
    assert value.gateway.create_conversation(*value.auth, value.ids["class"], value.ids["term"], value.thread, key,
        "合成人工会话", value.ids["student"]).status == "committed"
    statements = {
        "audit": "DELETE FROM class_os.business_audit WHERE action='command.commit' AND proposal_id IN (SELECT proposal_id FROM class_os.command_proposal WHERE command_type='conversation.create')",
        "receipt-hash": "UPDATE class_os.command_receipt SET payload_hash=repeat('0',64) WHERE resource_version=1 AND resource_id=:thread",
        "receipt-version": "UPDATE class_os.command_receipt SET resource_version=2 WHERE resource_version=1 AND resource_id=:thread",
        "command": "UPDATE class_os.command_proposal SET command_type='conversation.rename',payload=jsonb_set(payload,'{command}',to_jsonb('conversation.rename'::text)) WHERE command_type='conversation.create'",
        "purpose": "UPDATE class_os.command_proposal SET purpose='manage-roster' WHERE command_type='conversation.create'",
    }
    with control[4].transaction() as connection:
        assert connection.execute(text(statements[fault]), {"thread": value.thread}).rowcount >= 1
    with pytest.raises(CommandRejected):
        value.gateway.create_conversation(*value.auth, value.ids["class"], value.ids["term"], value.thread, key,
            "合成人工会话", value.ids["student"])


@pytest.mark.db
def test_pending_denial_then_admitted_human_input_exit_and_checkpoint(world, target):
    recovered = ready(world, target)
    data, ids = recovered.data, world[5]
    gateway = ConversationInteractionGateway(data.identity, recovered.store, clock=lambda: data.clock[0])
    query = ConversationInteractionQuery(data.identity, recovered.store, clock=lambda: data.clock[0])
    thread, creation, send = uuid4(), uuid4(), uuid4()
    with pytest.raises(CommandRejected):
        gateway.create_conversation(*data.credentials, ids["class"], ids["term"], thread, creation, "合成恢复后会话", ids["student"])
    submit_admission(recovered, approve_admission(recovered))
    gateway.create_conversation(*data.credentials, ids["class"], ids["term"], thread, creation, "合成恢复后会话", ids["student"])
    status = gateway.enqueue(*data.credentials, ids["class"], ids["term"], thread, send, "合成恢复后新输入", "chat")
    assert status.status == "committed"
    reopened = ConversationInteractionQuery(data.identity, AdmissionStore(data.dbs["runtime"], data.restrictions), clock=lambda: data.clock[0])
    history = reopened.conversation_history(*data.credentials, ids["class"], ids["term"], thread)
    assert history.history.messages[0].content.text == "合成恢复后新输入"
    assert history.message_attributions[0]["attribution"]["created_by"] == str(data.owner)
    summary = query.conversation_exit_summary(*data.credentials)
    export = CreateConversationExit(uuid4(), summary.snapshot_hash)
    proposal = gateway.preview(*data.credentials, export)
    nonce = gateway.approve(*data.credentials, proposal.proposal_id, proposal.payload_hash)
    gateway.commit(*data.credentials, proposal.proposal_id, uuid4(), nonce)
    bundle = query.conversation_exit_download(*data.credentials, export.export_id).bundle
    assert validate_v6(bundle) and bundle["activation_allowed"] is False
    assert len(bundle["conversations"]["conversation_run"]) == 2
    backup = checkpoint(recovered)
    artifact = backup.create()
    checked = backup.check_current_restrictions(artifact, data.restrictions)
    assert checked["snapshot_integrity_verified"] and not checked["activation_allowed"]


@pytest.mark.db
@pytest.mark.parametrize("fault", ["student", "class", "term", "enrollment"])
def test_ineligible_current_scope_does_not_save_input(control, fault):
    value = prepared(control)
    control[7][0] += timedelta(seconds=1)
    statements = {
        "student": "UPDATE class_os.student SET status='inactive'",
        "class": "UPDATE class_os.school_class SET status='archived'",
        "term": "UPDATE class_os.academic_term SET status='archived'",
        "enrollment": "UPDATE class_os.enrollment SET valid_to=valid_from+interval '1 millisecond',status='inactive'",
    }
    with control[4].transaction() as connection:
        assert connection.execute(text(statements[fault])).rowcount == 1
    with pytest.raises(CommandRejected):
        enqueue(value)
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_turn")).scalar_one() == 0


@pytest.mark.db
def test_wrong_store_composition_is_a_controlled_denial(control):
    value = prepared(control)
    plain = ConversationBusinessStore(control[2].database, control[3])
    gateway = ConversationInteractionGateway(value.gateway.identity, plain, clock=lambda: control[7][0])
    query = ConversationInteractionQuery(value.gateway.identity, plain, clock=lambda: control[7][0])
    with pytest.raises(CommandRejected):
        gateway.create_conversation(*value.auth, value.ids["class"], value.ids["term"], uuid4(), uuid4(), "合成不支持的组合")
    with pytest.raises(CommandRejected):
        gateway.enqueue(*value.auth, value.ids["class"], value.ids["term"], value.thread, uuid4(), "合成未保存", "chat")
    with pytest.raises(CommandRejected):
        query.conversations(*value.auth, value.ids["class"], value.ids["term"])
