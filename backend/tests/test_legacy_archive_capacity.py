"""Owned synthetic history stays readable as audit grows; export is unchanged."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.application.workbench import WorkbenchQueryGateway
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.durable_agent import DurableChatRuntime
from test_workbench_composition import workbench, documents, control, storage, roster, identity
from test_workbench_export_projection import collect
from test_classroom_work_storage import classroom_work, workspace_chat


def grow_audit(query, owner, auth, count=12000, *, action='document.list'):
    current = query.context(*auth)
    query.page(*auth, current.class_id, current.term_id)
    with owner.transaction() as connection:
        source = connection.execute(text("""SELECT event_id FROM class_os.business_audit
            WHERE action=:action AND outcome='allowed' ORDER BY occurred_at,event_id LIMIT 1"""), {'action': action}).scalar_one()
        connection.execute(text("""INSERT INTO class_os.business_audit
            (event_id,workspace_id,actor_id,session_digest,purpose,action,outcome,occurred_at,
             proposal_id,payload_hash,receipt_id,resource_id,resource_version,class_id,term_id)
            SELECT gen_random_uuid(),a.workspace_id,a.actor_id,a.session_digest,a.purpose,a.action,a.outcome,a.occurred_at,
                a.proposal_id,a.payload_hash,a.receipt_id,a.resource_id,a.resource_version,a.class_id,a.term_id
            FROM class_os.business_audit a CROSS JOIN generate_series(1,:count) WHERE a.event_id=:source"""),
            {'count': count, 'source': source})
        return connection.execute(text('SELECT count(*) FROM class_os.business_audit')).scalar_one()


async def completed_history(business, query, auth):
    current = query.context(*auth)
    thread = uuid4()
    business.create_conversation(*auth, current.class_id, current.term_id, thread, uuid4(), '合成历史班务讨论')
    runtime = DurableChatRuntime(business, query, PydanticAgentRuntime(query))
    events = [event async for event in runtime.stream(auth, current.class_id, current.term_id,
        thread, uuid4(), '查询已有班级记录和待办', 'read')]
    assert any(event.type == 'run.completed' for event in events)
    return auth, current, thread, query.conversation_page(*auth, current.class_id, current.term_id, thread)


@pytest.mark.db
async def test_history_with_original_sources_survives_large_audit_without_truncation_or_export_permission(workbench, monkeypatch):
    auth, current, thread, before = await completed_history(workbench[0], workbench[1], workbench[5][6])
    count = grow_audit(workbench[1], workbench[3], auth)
    assert count > 10000 and len(before.value.history.messages) == 2 and before.value.results
    query = workbench[1]
    listing = query.conversation_listing(*auth, current.class_id, current.term_id)
    assert listing.items[0]['thread_id'] == thread
    from class_os.domain import workbench_audit
    original = workbench_audit.partition_audit
    chunks = []
    def checked(rows, *args, **kwargs):
        chunks.append(len(rows))
        return original(rows, *args, **kwargs)
    with workbench[3].transaction(read_only=True) as connection:
        expected_rows = connection.execute(text('SELECT count(*) FROM class_os.business_audit')).scalar_one()
    with monkeypatch.context() as patch:
        patch.setattr(workbench_audit, 'partition_audit', checked)
        after = query.conversation_page(*auth, current.class_id, current.term_id, thread)
    assert sum(chunks) == expected_rows and max(chunks) <= 128
    assert after == before
    rebuilt = WorkbenchQueryGateway(workbench[0].identity, workbench[2], clock=query.clock)
    assert rebuilt.conversation_page(*auth, current.class_id, current.term_id, thread) == before
    with pytest.raises(CommandRejected):
        collect(workbench)  # Complete export keeps the original row/byte limits.
    with workbench[3].transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.business_audit')).scalar_one() >= count
        assert connection.execute(text('SELECT count(*) FROM class_os.conversation_message')).scalar_one() == 2
        assert connection.execute(text('SELECT count(*) FROM class_os.export_job')).scalar_one() == 0


@pytest.mark.db
@pytest.mark.parametrize('damage', ['unrelated-tail', 'source', 'completion'])
async def test_large_audit_still_refuses_bad_rows_and_missing_original_result_evidence(workbench, damage):
    auth, current, thread, _ = await completed_history(workbench[0], workbench[1], workbench[5][6])
    grow_audit(workbench[1], workbench[3], auth)
    with workbench[3].transaction() as connection:
        if damage == 'unrelated-tail':
            # The final ordered chunk must be checked even though none of its
            # document-read rows are needed to render this conversation.
            connection.execute(text("""UPDATE class_os.business_audit SET purpose='exit-recovery'
                WHERE event_id=(SELECT event_id FROM class_os.business_audit
                    WHERE action='document.list' ORDER BY occurred_at DESC,event_id DESC LIMIT 1)"""))
        else:
            action = 'activity.today' if damage == 'source' else 'command.commit'
            purpose = 'manage-class' if damage == 'source' else 'manage-conversation'
            connection.execute(text("""UPDATE class_os.business_audit SET payload_hash=:hash
                WHERE action=:action AND purpose=:purpose"""),
                {'hash': 'f' * 64, 'action': action, 'purpose': purpose})
    with pytest.raises((CommandRejected, ValueError)):
        workbench[1].conversation_page(*auth, current.class_id, current.term_id, thread)


@pytest.mark.db
async def test_current_classroom_profile_keeps_legacy_history_and_sources_after_large_audit(classroom_work):
    business, query, auth, owner, _, _, _, _, _, _ = classroom_work
    auth, current, thread, before = await completed_history(business, query, auth)
    count = grow_audit(query, owner, auth)
    assert count > 10000 and before.value.results
    assert query.conversation_listing(*auth, current.class_id, current.term_id).items[0]['thread_id'] == thread
    assert query.conversation_page(*auth, current.class_id, current.term_id, thread) == before
