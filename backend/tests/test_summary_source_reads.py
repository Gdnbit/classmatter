"""Fresh QG sources for factual document drafts; no model business writes."""
from uuid import uuid4

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
