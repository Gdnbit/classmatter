"""Synthetic SQL outcome transaction; original SDK integration is tested separately."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.conversation_worker import ConversationWorkerGateway
from class_os.application.result_capture import ResultCapture
from class_os.application.roster import CommandRejected
from class_os.domain.activity import CreateTask
from class_os.domain.conversation_results import ProducedResult
from test_conversation_interaction_gateway import prepared
from test_conversation_control import control, storage, roster, identity


def captured(control, mode):
    value = prepared(control)
    value.thread, value.key = uuid4(), uuid4()
    value.gateway.create_conversation(*value.auth, value.ids["class"], value.ids["term"], value.thread, uuid4(), "synthetic typed outcome")
    value.worker = ConversationWorkerGateway(value.gateway.identity, value.store, clock=lambda: control[7][0])
    value.worker.enqueue(*value.auth, value.ids["class"], value.ids["term"], value.thread, value.key, "synthetic input", mode)
    value.ticket = value.worker.claim(value.auth, value.ids["class"], value.ids["term"], value.thread, value.key)
    value.capture = ResultCapture(value.ticket, value.auth, value.query)
    sdk = uuid4()
    value.capture.begin(sdk, value.auth)
    if mode == "read":
        projection = value.query.work_snapshot(*value.auth, value.ids["class"], value.ids["term"])
        value.capture.observe_read(sdk, value.auth, projection)
    if mode == "draft":
        value.capture.observe_draft(sdk, value.auth, CreateTask("task.create", uuid4(), value.ids["class"], value.ids["term"], "synthetic candidate"))
    value.capture.completed(sdk, value.auth, "synthetic unverified answer")
    value.result = ProducedResult("synthetic unverified answer", value.capture.sources, value.capture.draft)
    value.sealed = value.capture.seal(sdk, value.auth, value.result)
    return value


@pytest.mark.db
@pytest.mark.parametrize("mode", ["chat", "read", "draft"])
def test_atomic_fixed_outcome_and_metadata_only_proposal(control, mode):
    value = captured(control, mode)
    receipt = value.worker.finish_result(value.auth, value.ticket, value.sealed)
    assert receipt.receipt.version == 3
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_query_source")).scalar_one() == (mode == "read")
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_task_draft")).scalar_one() == (mode == "draft")
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
        payload = connection.execute(text("SELECT payload FROM class_os.command_proposal WHERE command_type='conversation.run.finish-result'")).scalar_one()
        assert payload["result_hash"] == value.result.result_hash and "synthetic" not in str(payload)
    history = value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread)
    assert history.history.messages[-1].content.text == value.result.text
    with pytest.raises(CommandRejected):
        value.worker.finish_result(value.auth, value.ticket, value.sealed)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["audit", "source-audit", "closed-capture"])
def test_no_partial_body_sources_or_draft_after_failure(control, monkeypatch, fault):
    value = captured(control, "read")
    error = CommandRejected
    if fault == "source-audit":
        with control[4].transaction() as connection:
            connection.execute(text("DELETE FROM class_os.business_audit WHERE event_id=:id"), {"id": value.result.sources[0].receipt_id})
    elif fault == "closed-capture":
        value.capture.close()
    else:
        monkeypatch.setattr(value.store, "audit", lambda *args: None)
        error = AuditUnavailable
    with pytest.raises(error):
        value.worker.finish_result(value.auth, value.ticket, value.sealed)
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE role='assistant'")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_query_source")).scalar_one() == 0
        assert connection.execute(text("SELECT state FROM class_os.conversation_run")).scalar_one() == "running"


@pytest.mark.db
@pytest.mark.parametrize("mode", ["read", "draft"])
@pytest.mark.parametrize("fault", ["whole-metadata", "receipt", "proposal", "commit-audit"])
def test_history_never_downgrades_typed_result_after_corruption(control, mode, fault):
    value = captured(control, mode)
    value.worker.finish_result(value.auth, value.ticket, value.sealed)
    statements = {
        "whole-metadata": "DELETE FROM class_os." + ("conversation_query_source" if mode == "read" else "conversation_task_draft"),
        "receipt": "DELETE FROM class_os.conversation_result_receipt",
        "proposal": "UPDATE class_os.command_proposal SET payload=jsonb_set(payload,'{result_hash}',to_jsonb(repeat('f',64))) WHERE command_type='conversation.run.finish-result'",
        "commit-audit": "DELETE FROM class_os.business_audit WHERE proposal_id IN (SELECT proposal_id FROM class_os.command_proposal WHERE command_type='conversation.run.finish-result')",
    }
    with control[4].transaction() as connection:
        assert connection.execute(text(statements[fault])).rowcount == 1
    with pytest.raises((CommandRejected, ValueError)):
        value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread)


@pytest.mark.db
@pytest.mark.parametrize("mode", ["read", "draft", "chat"])
def test_controlled_clear_removes_plaintext_but_preserves_digest_only_outcome(control, mode):
    from class_os.domain.conversation_control import ClearConversation
    value = captured(control, mode)
    value.worker.finish_result(value.auth, value.ticket, value.sealed)
    history = value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread)
    proposal = value.worker.preview(*value.auth, ClearConversation(value.thread, value.ids["class"], value.ids["term"], history.history.version))
    nonce = value.worker.approve(*value.auth, proposal.proposal_id, proposal.payload_hash)
    value.worker.commit(*value.auth, proposal.proposal_id, uuid4(), nonce)
    assert not value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread).results
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE body IS NOT NULL AND thread_id=:thread"), {"thread": value.thread}).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_task_draft WHERE title IS NOT NULL")).scalar_one() == 0
        assert connection.execute(text("SELECT result_hash FROM class_os.conversation_result_receipt")).scalar_one() == value.result.result_hash


@pytest.mark.db
def test_clear_then_remove_entire_result_rejects_history_and_export(control):
    from class_os.domain.conversation_control import ClearConversation
    from class_os.domain.conversation_results import RESULT_COLUMNS
    value = captured(control, "draft")
    value.worker.finish_result(value.auth, value.ticket, value.sealed)
    history = value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread)
    proposal = value.worker.preview(*value.auth, ClearConversation(value.thread, value.ids["class"], value.ids["term"], history.history.version))
    nonce = value.worker.approve(*value.auth, proposal.proposal_id, proposal.payload_hash)
    value.worker.commit(*value.auth, proposal.proposal_id, uuid4(), nonce)
    with control[4].transaction() as connection:
        for table in RESULT_COLUMNS:
            connection.execute(text("DELETE FROM class_os." + table))
    for read in (lambda: value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread),
                 lambda: value.query.conversation_exit_summary(*value.auth)):
        with pytest.raises((CommandRejected, ValueError)):
            read()
