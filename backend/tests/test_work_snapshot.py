from uuid import uuid4
from contextlib import contextmanager
from datetime import timedelta
import json

import pytest
from sqlalchemy import text

from class_os.application.agent import AgentRequest, Mode
from class_os.application.roster import AuditUnavailable, CommandRejected
from class_os.domain.activity import CreateTask, ChangeTask
from class_os.infrastructure.agent import PydanticAgentRuntime
from test_activity_gateway import seed, submit
from test_roster_gateway import roster, class_command
from test_identity import identity


@pytest.mark.db
async def test_large_aggregate_has_one_real_receipt_covering_all_source_versions(roster):
    gateway, query, _, credentials, _, owner, _ = roster
    classroom, _, _ = seed(roster)
    tasks = []
    for index in range(120):
        item = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, f"合成统计跟进{index}")
        submit(gateway, credentials, item)
        tasks.append(item)
    before = query.work_snapshot(*credentials, classroom.class_id, classroom.term_id)
    assert before.open_tasks == 120 and before.record_count == 0
    payload = before.tool_payload()
    assert len(payload["source_refs"]) == 1 and len(json.dumps(payload)) < 2000
    with owner.transaction(read_only=True) as connection:
        persisted = connection.execute(text("SELECT workspace_id,payload_hash,purpose,resource_id FROM class_os.business_audit WHERE event_id=:id"), {"id": before.audit_id}).one()
        assert persisted.workspace_id == credentials[-1] and persisted.payload_hash == before.source_hash
        assert persisted.purpose == "manage-class" and persisted.resource_id == classroom.class_id
    submit(gateway, credentials, ChangeTask("task.complete", tasks[-1].task_id, classroom.class_id, classroom.term_id, 1, "done", "合成统计核对完成"))
    after = query.work_snapshot(*credentials, classroom.class_id, classroom.term_id)
    assert after.open_tasks == 119 and after.source_hash != before.source_hash and after.audit_id != before.audit_id
    runtime = PydanticAgentRuntime(query)
    conversation = runtime.conversation(credentials)
    events = [event async for event in runtime.stream(credentials, AgentRequest(conversation.conversation_id, "合成统计查询", Mode.READ))]
    assert events[-1].type == "run.completed"
    answer = next(event for event in events if event.type == "message.delta")
    assert "119" in answer.payload["text"] and len(answer.payload["source_refs"]) == 1


@pytest.mark.db
def test_snapshot_audit_failure_or_fake_receipt_cannot_release_projection(roster, monkeypatch):
    _, query, store, credentials, _, _, _ = roster
    classroom, _, _ = seed(roster)
    monkeypatch.setattr(store, "audit", lambda *args: None)
    with pytest.raises(RuntimeError, match="receipt"):
        query.work_snapshot(*credentials, classroom.class_id, classroom.term_id)
    monkeypatch.setattr(store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("injected")))
    with pytest.raises(RuntimeError):
        query.work_snapshot(*credentials, classroom.class_id, classroom.term_id)


@pytest.mark.db
def test_database_suppressed_insert_cannot_fabricate_a_query_receipt(roster):
    _, query, _, credentials, _, owner, _ = roster
    classroom, _, _ = seed(roster)
    with owner.transaction() as connection:
        connection.execute(text("""CREATE FUNCTION class_os.suppress_test_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.action='activity.today' THEN RETURN NULL; END IF; RETURN NEW; END $$"""))
        connection.execute(text("""CREATE TRIGGER suppress_test_audit BEFORE INSERT ON class_os.business_audit
            FOR EACH ROW EXECUTE FUNCTION class_os.suppress_test_audit()"""))
    with pytest.raises(AuditUnavailable):
        query.work_snapshot(*credentials, classroom.class_id, classroom.term_id)


@pytest.mark.db
def test_waiting_for_business_lock_cannot_extend_an_expired_approval(roster, monkeypatch):
    gateway, _, store, credentials, _, owner, clock = roster
    proposal = gateway.preview(*credentials, class_command())
    proof = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    original = store.atomic

    @contextmanager
    def delayed_lock():
        with original() as transaction:
            clock[0] += timedelta(minutes=11)
            yield transaction

    monkeypatch.setattr(store, "atomic", delayed_lock)
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, proposal.proposal_id, uuid4(), proof)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.school_class")).scalar_one() == 0
