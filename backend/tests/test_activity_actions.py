"""Synthetic ordinary-fact → linked follow-up → waiting → terminal lifecycle."""
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic_ai import CallDeferred, ModelRetry
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from class_os.domain.activity import CreateRecord, ReviseRecord, CreateTask, ChangeTask
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
    except ModelRetry:
        answer = {'repair': 'invalid-model-quote'}
    return capture.proposed, answer


@pytest.mark.db
async def test_shortened_model_name_requires_one_explicit_canonical_user_name(classroom_work):
    _, query, auth, _, _, _, _, _, _, students = classroom_work
    fact = '合成学生0交来展示作品'
    proposed, _ = await prepare(query, auth, '刚刚' + fact, 'prepare_record',
        {'student_name': '学生0', 'fact_text': fact, 'occurred_now': True})
    assert proposed['student_id'] == str(students[0])
    for message, short_name, quote in [
        ('刚刚学生0交来展示作品', '学生0', '交来展示作品'),
        ('刚刚合成学生0和合成学生1交来展示作品', '学生', '交来展示作品'),
        ('刚刚合成学生0交来展示作品', '不存在', fact),
    ]:
        proposed, _ = await prepare(query, auth, message, 'prepare_record',
            {'student_name': short_name, 'fact_text': quote, 'occurred_now': True})
        assert proposed is None


@pytest.mark.db
async def test_continuation_tool_precondition_blocks_unverified_repeated_record_then_allows_linked_task(classroom_work):
    business, query, auth, _, clock, store, commit, c, t, students = classroom_work
    fact = '合成学生0交来展示作品'
    record = CreateRecord('record.create', uuid4(), c, t, students[0], 'ordinary_fact', clock[0], fact, '')
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    thread, request = uuid4(), uuid4()
    chats.send(auth, thread, request, '刚刚' + fact + '，建立合成核对任务')
    chats.finish(auth, chats.claim(auth, thread, request), 'completed', '请核对。', record.canonical())
    commit(record)
    progress_calls = []
    def progress():
        progress_calls.append(True)
        return history.history(auth, thread)
    capture = WorkspaceActionCapture(('刚刚' + fact + '，建立合成核对任务', '继续完成上面的任务，只处理尚未完成的步骤。'),
        progress_reader=progress, classroom_enabled=True)
    tools = {tool.__name__: tool for tool in capture.tools(query, auth, lambda: None, lambda *a, **k: None)}
    denied = await tools['prepare_record'](student_name='合成学生0', fact_text=fact, occurred_now=True)
    assert denied['status'] == 'read-progress-first' and capture.proposed is None
    assert not capture.reads and not progress_calls
    await tools['read_task_progress']()
    assert capture.committed_record_ids == {str(record.record_id)}
    reused = await tools['prepare_record'](student_name='合成学生0', fact_text=fact, occurred_now=True)
    assert reused['status'] == 'existing-record' and reused['record_id'] == str(record.record_id)
    assert capture.proposed is None
    narrower = await tools['prepare_record'](student_name='合成学生0', fact_text='交来展示作品', occurred_now=True)
    assert narrower['status'] == 'read-source-first' and capture.proposed is None
    assert 'record_id' not in narrower  # A partial quote is not an automatic source match.
    missing_source = await tools['prepare_task'](action='create', title='合成核对任务')
    assert missing_source['status'] == 'read-source-first' and capture.proposed is None
    unread_source = await tools['prepare_task'](action='create', title='合成核对任务', student_name='合成学生0', source_fact=fact)
    assert unread_source['status'] == 'read-source-first' and capture.proposed is None
    await tools['read_class_records']()
    with pytest.raises(ModelRetry):
        await tools['prepare_task'](action='create', title='合成核对任务', student_name='合成学生0', source_fact='交来展示作品')
    assert capture.proposed is None
    assert capture.repair_requires_progress
    blocked = await tools['prepare_task'](action='create', title='合成核对任务', student_name='合成学生0', source_fact=fact)
    assert blocked['status'] == 'read-progress-first' and capture.proposed is None
    await tools['read_task_progress']()
    assert not capture.repair_requires_progress
    with pytest.raises(CallDeferred):
        await tools['prepare_task'](action='create', title='合成核对任务', student_name='合成学生0', source_fact=fact)
    assert progress_calls == [True, True] and capture.proposed['command'] == 'task.create'
    assert capture.proposed['source_record_id'] == str(record.record_id)
    value = query.projection(*auth, c, t)
    assert len(value['records']) == 1 and not value['tasks']
    unrelated = WorkspaceActionCapture(capture.user_messages, progress_reader=lambda: {'turns': [], 'next_before': None}, classroom_enabled=True)
    other = {tool.__name__: tool for tool in unrelated.tools(query, auth, lambda: None, lambda *a, **k: None)}
    await other['read_task_progress']()
    with pytest.raises(CallDeferred):
        await other['prepare_record'](student_name='合成学生0', fact_text=fact, occurred_now=True)
    assert unrelated.clarification == '这件事是什么时候发生的？' and unrelated.proposed is None
    standalone = WorkspaceActionCapture(('另外建立独立任务合成独立任务',), progress_reader=progress, classroom_enabled=True)
    separate = {tool.__name__: tool for tool in standalone.tools(query, auth, lambda: None, lambda *a, **k: None)}
    await separate['read_task_progress']()
    with pytest.raises(CallDeferred):
        await separate['prepare_task'](action='create', title='合成独立任务')
    assert standalone.proposed['source_record_id'] is None


@pytest.mark.db
@pytest.mark.parametrize('keeps_failing', [False, True])
async def test_sdk_repairs_its_bad_quote_without_asking_teacher_to_repeat_or_saving(classroom_work, keeps_failing):
    from pydantic_ai.messages import ModelResponse, ToolCallPart, RetryPromptPart
    from pydantic_ai.models.function import FunctionModel
    from class_os.infrastructure.agent import PydanticAgentRuntime
    from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
    business, query, auth, _, clock, store, _, c, t, _ = classroom_work
    calls = []
    fact = '合成学生0交来展示作品'
    def respond(messages, info):
        if calls:
            assert any(isinstance(part, RetryPromptPart) and 'exact quote' in str(part.content) for message in messages for part in message.parts)
        calls.append(True)
        if len(calls) == 2:
            assert [tool.name for tool in info.function_tools] == ['read_task_progress']
            return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
        return ModelResponse(parts=[ToolCallPart('prepare_record', {'student_name': '合成学生0',
            'fact_text': '模型改写了内容' if len(calls) == 1 or keeps_failing else fact, 'occurred_now': True})])
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    runtime = WorkspaceChatRuntime(chats, history, PydanticAgentRuntime(query, model_factory=lambda _: FunctionModel(respond)))
    thread, request = uuid4(), uuid4()
    chats.send(auth, thread, request, '刚刚' + fact + '，记下来')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    turn = history.turn(auth, thread, request)[1]
    assert len(calls) == 3
    if keeps_failing:
        assert not any(event.type in ('run.completed', 'message.delta', 'draft.available') for event in events)
        assert turn['candidate'] is turn['assistant_text'] is turn['change_preview'] is None
    else:
        assert any(event.type == 'run.completed' for event in events), runtime.sdk.last_failure_type
        assert turn['candidate']['fact_text'] == fact and turn['change_preview'] is not None
    assert turn['action_receipt'] is None
    assert not query.projection(*auth, c, t)['records']


@pytest.mark.db
async def test_rejected_historical_fact_reads_actual_progress_before_waiting(classroom_work):
    from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
    from pydantic_ai.models.function import FunctionModel
    from class_os.infrastructure.agent import PydanticAgentRuntime
    from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    thread, request = uuid4(), uuid4()
    fact, title, note = '合成学生0交来展示作品', '合成作品核对', '班长正在收集'
    record = CreateRecord('record.create', uuid4(), c, t, students[0], 'ordinary_fact', clock[0], fact, '')
    task = CreateTask('task.create', uuid4(), c, t, title, student_id=students[0], source_record_id=record.record_id)
    for command, message in ((record, '刚刚' + fact), (task, '根据这条记录建立' + title)):
        previous = uuid4()
        chats.send(auth, thread, previous, message)
        chats.finish(auth, chats.claim(auth, thread, previous), 'completed', '请核对。', command.canonical())
        commit(command)
    advertised, calls = [], []
    def respond(messages, info):
        advertised.append([tool.name for tool in info.function_tools])
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart('prepare_record', {'student_name': '学生0',
                'fact_text': '学生0交来展示作品', 'occurred_now': True})])
        if len(calls) == 2:
            assert advertised[-1] == ['read_task_progress'], advertised[-1]
            return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
        assert len(calls) == 3
        progress = next(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
        assert [(a['command'], a['status']) for a in progress['actions']] == [
            ('record.create', 'committed'), ('task.create', 'committed')]
        assert progress['active_request'] == title + '先等待，跟进记录原文为“' + note + '”'
        return ModelResponse(parts=[ToolCallPart('prepare_task', {'action': 'edit', 'title': title,
            'status': 'waiting', 'evidence': note})])
    sdk = PydanticAgentRuntime(query, model_factory=lambda _: FunctionModel(respond))
    runtime = WorkspaceChatRuntime(chats, history, sdk)
    chats.send(auth, thread, request, title + '先等待，跟进记录原文为“' + note + '”')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    turn = history.turn(auth, thread, request)[1]
    assert any(event.type == 'run.completed' for event in events), (sdk.last_failure_type, advertised)
    assert calls == [1, 2, 3] and turn['candidate']['command'] == 'task.update'
    assert turn['candidate']['evidence'] == note and turn['action_receipt'] is None
    state = query.projection(*auth, c, t)
    assert len(state['records']) == len(state['tasks']) == 1
    assert state['tasks'][0]['status'] == 'not-started' and state['tasks'][0]['version'] == 1
    assert next(f for f in turn['change_preview']['fields'] if f['field'] == 'status') == {
        'field': 'status', 'before': 'not-started', 'after': 'waiting'}
    preview = business.preview(*auth, candidate(turn['candidate']))
    approval = business.approve(*auth, preview.proposal_id, preview.payload_hash) if preview.risk == 'W2' else None
    attempt = uuid4()
    receipt = business.commit(*auth, preview.proposal_id, attempt, approval)
    assert business.commit(*auth, preview.proposal_id, attempt, approval) == receipt
    restored = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0]).turn(auth, thread, request)[1]
    assert restored['change_preview'] == turn['change_preview'] and restored['action_receipt']['version'] == 2
    state = query.projection(*auth, c, t)
    assert len(state['records']) == len(state['tasks']) == 1
    assert state['tasks'][0]['status'] == 'waiting' and state['tasks'][0]['version'] == 2
    assert state['tasks'][0]['evidence'] == note
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.record_revision')).scalar_one() == 1
        assert connection.execute(text('SELECT count(*) FROM class_os.command_receipt WHERE resource_id IN (:record, :task)'),
            {'record': record.record_id, 'task': task.task_id}).scalar_one() == 3


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
