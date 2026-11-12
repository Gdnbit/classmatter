"""Synthetic ordinary-fact → linked follow-up → waiting → terminal lifecycle."""
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic_ai import CallDeferred
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from class_os.domain.activity import CreateRecord, ReviseRecord, ChangeTask
from class_os.domain.workspace_chat import candidate
from class_os.infrastructure.workspace_actions import WorkspaceActionCapture
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


async def prepare(query, auth, message, name, arguments):
    capture = WorkspaceActionCapture((message,), classroom_enabled=True)
    tools = {tool.__name__: tool for tool in capture.tools(query, auth, lambda: None, lambda *a, **k: None)}
    try:
        answer = await tools[name](**arguments)
    except CallDeferred:
        answer = {'question': capture.clarification}
    return capture.proposed, answer


@pytest.mark.db
async def test_fact_linked_task_waiting_completion_comparisons_receipts_and_restart(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    thread = uuid4()
    async def step(message, tool, arguments):
        payload, _ = await prepare(query, auth, message, tool, arguments)
        assert payload is not None
        request = uuid4()
        chats.send(auth, thread, request, message)
        row = chats.finish(auth, chats.claim(auth, thread, request), 'completed', '请核对。', payload)
        comparison = row['change_preview']
        assert comparison['candidate_hash'] == row['candidate_hash']
        command = candidate(payload)
        preview = business.preview(*auth, command)
        approval = business.approve(*auth, preview.proposal_id, preview.payload_hash) if preview.risk == 'W2' else None
        attempt = uuid4()
        receipt = business.commit(*auth, preview.proposal_id, attempt, approval)
        assert business.commit(*auth, preview.proposal_id, attempt, approval) == receipt
        rebuilt = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
        saved = rebuilt.turn(auth, thread, request)[1]
        assert saved['change_preview'] == comparison and saved['action_receipt']['resource_id'] == receipt.resource_id
        return payload, comparison

    fact = '合成学生0交来展示作品'
    record, comparison = await step('刚刚' + fact, 'prepare_record',
        {'student_name': '合成学生0', 'fact_text': fact, 'occurred_now': True})
    assert comparison['kind'] == 'create' and comparison['fields'][1]['after'] == fact
    deadline = (clock[0] + timedelta(days=1)).isoformat()
    task, _ = await step('根据合成学生0交来展示作品，建立任务合成作品核对，截止' + deadline, 'prepare_task',
        {'action': 'create', 'title': '合成作品核对', 'student_name': '合成学生0', 'source_fact': fact, 'due_at': deadline})
    assert task['source_record_id'] == record['record_id']
    _, waiting = await step('合成作品核对先等待，班长正在收集', 'prepare_task',
        {'action': 'edit', 'title': '合成作品核对', 'status': 'waiting', 'evidence': '班长正在收集'})
    assert next(field for field in waiting['fields'] if field['field'] == 'status') == {'field': 'status', 'before': 'not-started', 'after': 'waiting'}
    finished, completed = await step('合成作品核对已完成，班长交齐，我已核对', 'prepare_task',
        {'action': 'complete', 'title': '合成作品核对', 'evidence': '班长交齐，我已核对'})
    assert finished['command'] == 'task.complete'
    assert next(field for field in completed['fields'] if field['field'] == 'evidence')['before'] == '班长正在收集'
    assert next(field for field in completed['fields'] if field['field'] == 'status')['after'] == 'done'
    projection = query.projection(*auth, c, t)
    assert len(projection['records']) == len(projection['tasks']) == 1
    assert projection['tasks'][0]['version'] == 3 and projection['tasks'][0]['status'] == 'done'
    assert projection['tasks'][0]['source_record_id'] == projection['records'][0]['record_id']
    assert history.history(auth, thread)['turns'][2]['change_preview'] == waiting
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.command_receipt WHERE resource_id=:id'),
            {'id': projection['tasks'][0]['task_id']}).scalar_one() == 3


@pytest.mark.db
async def test_missing_fabricated_ambiguous_terminal_and_stale_inputs_do_not_write(classroom_work):
    business, query, auth, owner, clock, _, commit, c, t, students = classroom_work
    cases = [
        ('记录合成学生0的作品', 'prepare_record', {'student_name': '合成学生0', 'fact_text': '模型猜测'}),
        ('合成学生0交来作品', 'prepare_record', {'student_name': '合成学生0', 'fact_text': '交来作品', 'occurred_now': True}),
        ('刚刚合成学生0交来作品', 'prepare_record', {'student_name': '不存在', 'fact_text': '交来作品', 'occurred_now': True}),
        ('建立合成跟进', 'prepare_task', {'action': 'create', 'title': '合成跟进', 'due_at': '2026-11-15T17:00:00+08:00'}),
        ('根据合成学生0的交来作品建立合成跟进', 'prepare_task', {'action': 'create', 'title': '合成跟进', 'student_name': '合成学生0', 'source_fact': '交来作品'}),
    ]
    for message, tool, arguments in cases:
        payload, _ = await prepare(query, auth, message, tool, arguments)
        assert payload is None
    from class_os.domain.activity import CreateTask
    task = CreateTask('task.create', uuid4(), c, t, '合成跟进')
    commit(task)
    old_claim = WorkspaceActionCapture(('合成跟进计划交齐，我已核对', '结束合成跟进'), classroom_enabled=True)
    terminal = next(tool for tool in old_claim.tools(query, auth, lambda: None, lambda *a, **k: None) if tool.__name__ == 'prepare_task')
    with pytest.raises(CallDeferred):
        await terminal(action='complete', title='合成跟进', evidence='我已核对')
    assert old_claim.proposed is None and old_claim.clarification == '请补充实际完成结果。'
    for arguments in (
        {'action': 'complete'}, {'action': 'cancel'}, {'action': 'complete', 'evidence': '模型猜测已交齐'},
        {'action': 'complete', 'evidence': '已核对', 'new_title': '合成新标题'},
    ):
        payload, _ = await prepare(query, auth, '合成跟进已核对，改为合成新标题', 'prepare_task', {'title': '合成跟进', **arguments})
        assert payload is None
    stale, _ = await prepare(query, auth, '合成跟进已核对', 'prepare_task', {'title': '合成跟进', 'action': 'complete', 'evidence': '已核对'})
    commit(ChangeTask('task.update', task.task_id, c, t, 1, 'waiting', '等待补充'))
    with pytest.raises(CommandRejected):
        business.preview(*auth, candidate(stale))
    cancelled, _ = await prepare(query, auth, '合成跟进取消，不再需要', 'prepare_task', {'title': '合成跟进', 'action': 'cancel', 'evidence': '不再需要'})
    commit(candidate(cancelled))
    again, _ = await prepare(query, auth, '合成跟进已核对', 'prepare_task', {'title': '合成跟进', 'action': 'complete', 'evidence': '已核对'})
    assert again is None
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.record_revision')).scalar_one() == 0
        assert connection.execute(text('SELECT status FROM class_os.manual_task')).scalar_one() == 'cancelled'


@pytest.mark.db
async def test_read_sources_latest_corrected_only_and_preserve_waiting_evidence(classroom_work):
    _, query, auth, _, clock, _, commit, c, t, students = classroom_work
    record = CreateRecord('record.create', uuid4(), c, t, students[0], 'ordinary_fact', clock[0], '原来的作品记录', '')
    commit(record)
    commit(ReviseRecord('record.correct', record.record_id, c, t, 1, '核对后的作品记录', '', '合成核对'))
    capture = WorkspaceActionCapture(('查询合成学生0',), classroom_enabled=True)
    tool = next(tool for tool in capture.tools(query, auth, lambda: None, lambda *a, **k: None) if tool.__name__ == 'read_class_records')
    result = await tool(student_name='合成学生0')
    assert len(result['items']) == 1 and result['items'][0]['fact_text'] == '核对后的作品记录'
    assert result['items'][0]['version'] == 2 and result['items'][0]['record_id'] == str(record.record_id)
    commit(ReviseRecord('record.supersede', record.record_id, c, t, 2, '作废', '', '合成作废'))
    assert (await tool(student_name='合成学生0'))['items'] == []
    deadline = (clock[0] + timedelta(days=1)).isoformat()
    payload, _ = await prepare(query, auth, '建立合成期限任务，截止' + deadline, 'prepare_task',
        {'action': 'create', 'title': '合成期限任务', 'due_at': deadline})
    commit(candidate(payload))
    waiting, _ = await prepare(query, auth, '合成期限任务等待补交', 'prepare_task',
        {'action': 'edit', 'title': '合成期限任务', 'status': 'waiting', 'evidence': '等待补交'})
    commit(candidate(waiting))
    renamed, _ = await prepare(query, auth, '合成期限任务改成合成核对任务', 'prepare_task',
        {'action': 'edit', 'title': '合成期限任务', 'new_title': '合成核对任务'})
    assert renamed['evidence'] == '等待补交' and 'due_at' not in renamed
    commit(candidate(renamed))
    assert query.projection(*auth, c, t)['tasks'][0]['due_at'].isoformat() == deadline
    cleared, _ = await prepare(query, auth, '合成核对任务去掉截止时间', 'prepare_task',
        {'action': 'edit', 'title': '合成核对任务', 'change_due_date': True})
    commit(candidate(cleared))
    row = query.projection(*auth, c, t)['tasks'][0]
    assert row['due_at'] is None and row['status'] == 'waiting' and row['evidence'] == '等待补交'
