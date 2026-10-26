"""Actual SDK -> PG -> single-hop recovery -> clear -> real restored checkpoint."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.conversation_interaction import ConversationInteractionQuery
from class_os.application.conversation_worker import ConversationWorkerGateway
from class_os.application.recovery_admission import AdmissionGateway, AdmissionQueryGateway, AuthorizedRetirementReader
from class_os.domain.conversation_control import ClearConversation
from class_os.domain.recovery_admission import AdmitConversationTarget
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.durable_agent import DurableChatRuntime
from class_os.infrastructure.recovery_admission_store import AdmissionStore
from test_source_retirement_gateway import world, target, control, storage, roster, identity, retirement, approve_retirement, commit_retirement
from test_target_import_gateway import prepare, approved, commit
from test_recovery_admission_gateway import approve, submit, checkpoint, native
from test_recovery_admission_gateway import ready


@pytest.mark.db
@pytest.mark.parametrize("mode", ["read", "draft"])
async def test_actual_typed_result_single_hop_and_clear_checkpoint(world, target, mode):
    ids, credentials = world[5], world[6]
    # Only the raw, never-dispatched fixture run; do not rewrite SDK outcomes.
    with world[4].transaction() as connection:
        assert connection.execute(text("""UPDATE class_os.conversation_run SET state='cancelled',version=2,ended_at=created_at
            WHERE workspace_id=:workspace AND run_id=:run AND state='queued'"""), ids).rowcount == 1
    source_store = AdmissionStore(world[2].database, world[3])
    worker = ConversationWorkerGateway(world[0].identity, source_store, clock=world[0].clock)
    query = ConversationInteractionQuery(world[0].identity, source_store, clock=world[0].clock)
    thread, key = uuid4(), uuid4()
    worker.create_conversation(*credentials, ids["class"], ids["term"], thread, uuid4(), "synthetic transferable result")
    runtime = DurableChatRuntime(worker, query, PydanticAgentRuntime(query))
    events = [item async for item in runtime.stream(credentials, ids["class"], ids["term"], thread, key, "synthetic class task", mode)]
    assert events[-1].type == "run.completed"
    before = query.conversation_history(*credentials, ids["class"], ids["term"], thread).results
    assert len(before) == 1
    data = prepare(world, target, terminal=False)
    assert data.artifact.bundle["schema_version"] == "classmatter.synthetic-exit.v6"
    commit(data, approved(data))
    _, retiring, source_query, command, _ = retirement(world, data)
    commit_retirement(world, retiring, approve_retirement(world, retiring, command))
    proof = source_query.committed_retirement(*credentials, command.attempt_id)
    store = AdmissionStore(data.dbs["runtime"], data.restrictions,
        AuthorizedRetirementReader(source_query, credentials, command.attempt_id))
    gateway = AdmissionGateway(data.identity, store, clock=lambda: data.clock[0])
    admitted_query = AdmissionQueryGateway(data.identity, store, clock=lambda: data.clock[0])
    summary = admitted_query.admission_summary(*data.credentials, command.attempt_id)
    value = SimpleNamespace(data=data, store=store, gateway=gateway, query=admitted_query,
        command=AdmitConversationTarget(command.attempt_id, proof.proof_hash, summary.stage_hash, summary.origins_hash))
    submit(value, approve(value))
    assert ids["owner"] != data.owner and credentials[3] != data.credentials[3]
    after = admitted_query.conversation_history(*data.credentials, ids["class"], ids["term"], thread)
    assert after.results == before and after.results[0].draft_status == "uncommitted"
    assert after.message_attributions[-1]["attribution"]["source_owner_id"] == str(ids["owner"])
    if mode == "read":
        source, = after.results[0].result.sources
        assert source.source_owner_id == ids["owner"] and source.source_workspace_id == credentials[3]
    native(value, ClearConversation(thread, ids["class"], ids["term"], after.history.version))
    assert not admitted_query.conversation_history(*data.credentials, ids["class"], ids["term"], thread).results
    backup = checkpoint(value)
    packet = backup.create()
    checked = backup.check_current_restrictions(packet, data.restrictions)
    assert checked["activation_allowed"] is False and checked["table_count"] == 35
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_result_receipt")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_task_draft WHERE title IS NOT NULL")).scalar_one() == 0


@pytest.mark.db
def test_old_empty_result_witness_clear_adds_verified_legacy_digest_after_admission(world, target):
    from datetime import timedelta
    value = ready(world, target, assistant=True, legacy_no_receipt=True)
    submit(value, approve(value))
    ids, data = world[5], value.data
    history = value.query.conversation_history(*data.credentials, ids["class"], ids["term"], ids["thread"])
    assert not history.results and len(history.history.messages) == 2
    data.clock[0] += timedelta(seconds=1)
    native(value, ClearConversation(ids["thread"], ids["class"], ids["term"], history.history.version))
    assert not value.query.conversation_history(*data.credentials, ids["class"], ids["term"], ids["thread"]).history.messages
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        row = connection.execute(text("SELECT protocol,text_hash,result_hash,created_at,recorded_at FROM class_os.conversation_result_receipt")).mappings().one()
        admitted = connection.execute(text("SELECT created_at FROM class_os.conversation_admission")).scalar_one()
        assert row["protocol"] == "legacy-plain" and row["text_hash"] == row["result_hash"]
        assert row["created_at"] < admitted < row["recorded_at"]
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_origin WHERE entity_kind='conversation_result_receipt'")).scalar_one() == 0
    backup = checkpoint(value)
    assert backup.check_current_restrictions(backup.create(), data.restrictions)["activation_allowed"] is False


@pytest.mark.db
def test_legacy_digest_expansion_rejected_before_irreversible_clear_marker(world, target, monkeypatch):
    from class_os.application.roster import CommandRejected
    from class_os.infrastructure import target_import_store
    value = ready(world, target, assistant=True, legacy_no_receipt=True)
    submit(value, approve(value))
    ids, data = world[5], value.data
    history = value.query.conversation_history(*data.credentials, ids["class"], ids["term"], ids["thread"])
    command = ClearConversation(ids["thread"], ids["class"], ids["term"], history.history.version)
    proposal = value.gateway.preview(*data.credentials, command)
    nonce = value.gateway.approve(*data.credentials, proposal.proposal_id, proposal.payload_hash)
    before = data.restrictions.read()
    original = target_import_store.validate_import_integrity
    def reject_expansion(connection):
        if connection.execute(text("SELECT count(*) FROM class_os.conversation_result_receipt")).scalar_one():
            raise ValueError("synthetic expanded budget denial")
        return original(connection)
    monkeypatch.setattr(target_import_store, "validate_import_integrity", reject_expansion)
    with pytest.raises(CommandRejected):
        value.gateway.commit(*data.credentials, proposal.proposal_id, uuid4(), nonce)
    assert data.restrictions.read() == before
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_result_receipt")).scalar_one() == 0
    assert value.query.conversation_history(*data.credentials, ids["class"], ids["term"], ids["thread"]).history.messages == history.history.messages
