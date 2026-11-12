"""Real SDK token accounting for the bounded classroom tool graph, offline."""
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from class_os.application.workbench import WorkbenchQueryGateway
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


@pytest.mark.db
@pytest.mark.parametrize('per_request,completed', [(3500, True), (9000, False)])
async def test_classroom_five_request_plan_fits_but_excess_usage_still_fails_before_writes(classroom_work, per_request, completed):
    business, query, auth, _, clock, store, _, c, t, _ = classroom_work
    reports, calls = [], []
    fact = '合成学生0交来展示作品'
    def respond(messages, info):
        calls.append(True)
        part = (ToolCallPart('read_class_work', {'kind': 'tasks'}) if len(calls) < 5 else
                ToolCallPart('prepare_record', {'student_name': '合成学生0', 'fact_text': fact, 'occurred_now': True}))
        return ModelResponse(parts=[part], usage=RequestUsage(input_tokens=per_request, output_tokens=20))
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    sdk = PydanticAgentRuntime(query, timeout=45, diagnostics=reports.append, model_factory=lambda _: FunctionModel(respond))
    runtime = WorkspaceChatRuntime(chats, history, sdk)
    thread, request = uuid4(), uuid4()
    chats.send(auth, thread, request, '刚刚' + fact + '，核对后准备记录')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    row = history.turn(auth, thread, request)[1]
    if completed:
        assert any(event.type == 'run.completed' for event in events), reports
        assert len(calls) == 5 and row['candidate']['fact_text'] == fact
        assert row['input_tokens'] == 17500 and row['output_tokens'] == 100
    else:
        assert not any(event.type in ('run.completed', 'message.delta', 'draft.available') for event in events)
        assert len(calls) == 4 and row['candidate'] is row['assistant_text'] is None
        assert any(report.get('category') == 'local_usage_limit' and report.get('limit') == 'total_tokens_limit' for report in reports)
    assert row['action_receipt'] is None and not query.projection(*auth, c, t)['records']


@pytest.mark.db
async def test_legacy_workspace_tools_retain_the_original_token_limit(workspace_chat):
    business, history, auth, _, _, clock, store, boundary = workspace_chat
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    reports, calls = [], []
    def respond(messages, info):
        calls.append(True)
        part = (ToolCallPart('read_task_progress', {}) if len(calls) < 5 else
                ToolCallPart('prepare_task', {'action': 'create', 'title': '合成任务'}) if len(calls) == 5 else TextPart('请告诉我班级。'))
        return ModelResponse(parts=[part], usage=RequestUsage(input_tokens=3500, output_tokens=20))
    sdk = PydanticAgentRuntime(query, timeout=45, diagnostics=reports.append, model_factory=lambda _: FunctionModel(respond))
    runtime = WorkspaceChatRuntime(business, history, sdk)
    thread, request = uuid4(), uuid4()
    business.send(auth, thread, request, '整理合成任务')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    assert not any(event.type in ('run.completed', 'message.delta', 'draft.available') for event in events)
    assert len(calls) == 5 and history.turn(auth, thread, request)[1]['candidate'] is None
    assert any(report.get('category') == 'local_usage_limit' and report.get('limit') == 'total_tokens_limit' for report in reports)
