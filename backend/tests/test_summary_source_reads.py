"""Fresh QG sources for factual document drafts; no model business writes."""
from uuid import uuid4
from threading import Event

import pytest
from pydantic_ai import CallDeferred
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from class_os.domain.activity import CreateRecord, CreateTask, ChangeTask
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.workspace_actions import WorkspaceActionCapture
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


@pytest.mark.db
@pytest.mark.parametrize('prepare_first', [False, True])
async def test_parallel_source_read_and_document_preparation_cannot_skip_task_source(classroom_work, monkeypatch, prepare_first):
    business, query, auth, _, clock, store, commit, c, t, students = classroom_work
    fact = CreateRecord('record.create', uuid4(), c, t, students[0], 'ordinary_fact', clock[0], '合成学生0交来作品', '')
    task = CreateTask('task.create', uuid4(), c, t, '合成作品核对', None, students[0], fact.record_id)
    commit(fact); commit(task)
    commit(ChangeTask('task.complete', task.task_id, c, t, 1, 'done', '班长交齐，我已核对'))
    attempted, source_finished, premature, rejected = Event(), Event(), [], []
    original = WorkspaceActionCapture.propose
    def observe_prepare(capture, command):
        premature.append(not source_finished.is_set())
        attempted.set()
        return original(capture, command)
    monkeypatch.setattr(WorkspaceActionCapture, 'propose', observe_prepare)
    def projection(*args, **kwargs):
        if not source_finished.is_set():
            # Hold the genuine QG source while the old concurrent preparation
            # can race it. A serialized SDK barrier releases after this bound.
            attempted.wait(1)
            result = query.projection(*args, **kwargs)
            source_finished.set()
            return result
        return query.projection(*args, **kwargs)
    class ReadObserver:
        def __getattr__(self, name):
            return projection if name == 'projection' else getattr(query, name)
    guarded_query = ReadObserver()
    def respond(messages, info):
        returned = [part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]
        if not returned:
            parts = [ToolCallPart('read_class_records', {}),
                ToolCallPart('prepare_document', {'action': 'create', 'title': '合成工作小结', 'body': '未经本轮任务来源核对'})]
            return ModelResponse(parts=list(reversed(parts)) if prepare_first else parts)
        if not any(part.tool_name == 'read_class_work' for part in returned):
            denied = next(part for part in returned if part.tool_name == 'prepare_document')
            assert denied.content['status'] == ('read-record-source-first' if prepare_first else 'read-task-source-first')
            rejected.append(True)
            return ModelResponse(parts=[ToolCallPart('read_class_work', {'kind': 'tasks'})])
        source = next(part.content['items'][0] for part in returned if part.tool_name == 'read_class_work')
        assert source['status'] == 'done' and source['version'] == 2
        return ModelResponse(parts=[ToolCallPart('prepare_document', {'action': 'create', 'title': '合成工作小结',
            'body': fact.fact_text + '；' + source['evidence']})])
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    sdk = PydanticAgentRuntime(guarded_query, timeout=45, model_factory=lambda _: FunctionModel(respond))
    runtime = WorkspaceChatRuntime(chats, history, sdk)
    thread, request = uuid4(), uuid4()
    chats.send(auth, thread, request, '根据已确认的普通事实和任务，生成合成工作小结。')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    row = history.turn(auth, thread, request)[1]
    assert premature == [False], 'A document cannot be prepared before its preceding source read completes'
    assert rejected == [True] and row['state'] == 'completed', sdk.last_failure_type
    assert row['candidate']['body'] == fact.fact_text + '；班长交齐，我已核对'
    assert row['action_receipt'] is None and not query.documents(*auth, c, t)
    assert any(event.type == 'draft.available' for event in events)


@pytest.mark.db
@pytest.mark.parametrize('shortened', [False, True])
@pytest.mark.parametrize('source_kind', ['record', 'task'])
async def test_sourced_document_repairs_internal_identifier_to_readable_citation(classroom_work, shortened, source_kind):
    business, query, auth, _, clock, store, commit, c, t, students = classroom_work
    fact = CreateRecord('record.create', uuid4(), c, t, students[0], 'ordinary_fact', clock[0], '合成学生0交来作品', '')
    task = CreateTask('task.create', uuid4(), c, t, '合成作品核对', None, students[0], fact.record_id)
    commit(fact); commit(task)
    rejected = []
    def respond(messages, info):
        returned = [part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]
        if not returned:return ModelResponse(parts=[ToolCallPart('read_class_records', {})])
        if not any(part.tool_name == 'read_class_work' for part in returned):
            return ModelResponse(parts=[ToolCallPart('read_class_work', {'kind': 'tasks'})])
        prepared = [part for part in returned if part.tool_name == 'prepare_document']
        if prepared:
            assert prepared[-1].content['status'] == 'readable-citations-required'
            rejected.append(True)
            body = '合成学生0交来作品；合成作品核对：尚未结束。'
        else:
            source = next(part.content['items'][0] for part in returned if part.tool_name ==
                ('read_class_records' if source_kind == 'record' else 'read_class_work'))
            identifier = source['record_id' if source_kind == 'record' else 'task_id']
            value = identifier.split('-')[0] + '...' if shortened else identifier
            body = '合成学生0交来作品，来源ID：' + value.upper()
        return ModelResponse(parts=[ToolCallPart('prepare_document', {'action': 'create', 'title': '合成工作小结', 'body': body})])
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    sdk = PydanticAgentRuntime(query, timeout=45, model_factory=lambda _: FunctionModel(respond))
    runtime = WorkspaceChatRuntime(chats, history, sdk)
    thread, request = uuid4(), uuid4()
    chats.send(auth, thread, request, '根据普通事实和任务，生成合成工作小结。')
    _ = [event async for event in runtime.stream_queued(auth, thread, request)]
    row = history.turn(auth, thread, request)[1]
    assert row['state'] == 'completed' and rejected == [True], sdk.last_failure_type
    assert row['candidate']['body'] == '合成学生0交来作品；合成作品核对：尚未结束。'
    assert row['action_receipt'] is None and not query.documents(*auth, c, t)


@pytest.mark.db
async def test_factual_document_reads_actual_task_result_not_only_receipt_progress(classroom_work):
    business, query, auth, _, clock, store, commit, c, t, students = classroom_work
    fact = CreateRecord('record.create', uuid4(), c, t, students[0], 'ordinary_fact', clock[0], '合成学生0交来作品', '')
    task = CreateTask('task.create', uuid4(), c, t, '合成作品核对', None, students[0], fact.record_id)
    commit(fact); commit(task)
    commit(ChangeTask('task.complete', task.task_id, c, t, 1, 'done', '班长交齐，我已核对'))
    calls, rejected, sources = [], [], {}
    def respond(messages, info):
        calls.append(True)
        returned = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
        if not returned:
            return ModelResponse(parts=[ToolCallPart('read_class_records', {})])
        last = returned[-1]
        if last.tool_name == 'read_class_records': sources['record'] = last.content['items'][0]
        if last.tool_name == 'prepare_document':
            assert last.content['status'] == 'read-task-source-first'
            rejected.append(True)
            return ModelResponse(parts=[ToolCallPart('read_task_progress' if len(rejected) == 1 else 'read_class_work', {} if len(rejected) == 1 else {'kind': 'tasks'})])
        if last.tool_name == 'read_class_work':
            sources['task'] = last.content['items'][0]
            assert sources['task']['status'] == 'done' and sources['task']['version'] == 2
        body = ('尚未读取任务的旧说法' if 'task' not in sources else
                sources['record']['fact_text'] + '；' + sources['task']['title'] + '：' + sources['task']['evidence'])
        return ModelResponse(parts=[ToolCallPart('prepare_document', {'action': 'create', 'title': '合成工作小结', 'body': body})])
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    sdk = PydanticAgentRuntime(query, timeout=45, model_factory=lambda _: FunctionModel(respond))
    runtime = WorkspaceChatRuntime(chats, history, sdk)
    thread, request = uuid4(), uuid4()
    chats.send(auth, thread, request, '根据已确认的普通事实和任务，生成合成工作小结。')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    row = history.turn(auth, thread, request)[1]
    assert row['state'] == 'completed' and row['candidate']['command'] == 'document.create', sdk.last_failure_type
    assert len(calls) == 6 and rejected == [True, True]
    assert row['candidate']['body'] == '合成学生0交来作品；合成作品核对：班长交齐，我已核对'
    assert row['action_receipt'] is None and not query.documents(*auth, c, t)
    assert any(event.type == 'draft.available' for event in events)
    assert query.projection(*auth, c, t)['tasks'][0]['version'] == 2


@pytest.mark.db
async def test_source_read_scope_is_per_turn_and_generic_document_remains_available(classroom_work):
    _, query, auth, _, _, _, _, c, t, _ = classroom_work
    first = WorkspaceActionCapture(('生成合成工作小结',), classroom_enabled=True)
    tools = {fn.__name__: fn for fn in first.tools(query, auth, lambda: None, lambda *a, **k: None)}
    await tools['read_class_records']()
    await tools['read_class_work'](kind='students')
    blocked = await tools['prepare_document'](action='create', title='合成工作小结', body='旧说法')
    assert blocked['status'] == 'read-task-source-first' and first.proposed is first.clarification is None
    assert first.record_read_scopes == {(c, t)} and first.task_read_scopes == set()
    second = WorkspaceActionCapture(('创建合成教案，正文是课堂讨论提纲',), classroom_enabled=True)
    fresh = {fn.__name__: fn for fn in second.tools(query, auth, lambda: None, lambda *a, **k: None)}
    assert not second.record_read_scopes and not second.task_read_scopes
    with pytest.raises(CallDeferred):
        await fresh['prepare_document'](action='create', title='合成教案', body='课堂讨论提纲')
    assert second.proposed['body'] == '课堂讨论提纲' and not query.documents(*auth, c, t)
