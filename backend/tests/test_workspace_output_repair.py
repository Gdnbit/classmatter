"""SDK-owned bounded repair for the false-ready reply found in live acceptance."""
from uuid import uuid4
import httpx
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart, RetryPromptPart
from pydantic_ai.models.function import FunctionModel
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity

CONTINUE = '继续完成上面的任务，只处理尚未完成的步骤。'
FALSE_READY = '第三步已准备就绪：建立一个2排3座的座位表。请确认是否执行？'


@pytest.mark.db
@pytest.mark.parametrize('case', ['repair', 'exhausted', 'ordinary'])
async def test_continuation_needs_a_real_candidate_and_repairs_are_bounded(classroom_work, case):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    attempts, repairs = [], []
    def factory(request):
        def respond(messages, info):
            if request.text == '以后帮我建立2排3座的座位表。':
                return ModelResponse(parts=[TextPart('收到。')])
            attempts.append(True)
            if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
                return ModelResponse(parts=[TextPart(FALSE_READY)])
            if any(isinstance(part, RetryPromptPart) for part in messages[-1].parts):
                repairs.append(True)
                if case == 'repair':
                    return ModelResponse(parts=[ToolCallPart('prepare_seat_layout', {'rows': 2, 'columns': 3})])
            return ModelResponse(parts=[TextPart(FALSE_READY)])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory, timeout=45)
    app = create_workspace_chat_app(Settings(), worker=business, query=query, sdk=sdk)
    cookies = dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    prefix = f'/api/workspaces/{auth[3]}/workspace-chat/threads/{uuid4()}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000', cookies=cookies) as client:
        for text in ('以后帮我建立2排3座的座位表。', CONTINUE if case != 'ordinary' else '仅讨论这段文字，不执行任何操作。'):
            request = uuid4()
            assert (await client.post(prefix + '/turns', headers=headers, json={'request_id': str(request), 'text': text})).status_code == 200
            wire = await client.post(prefix + f'/turns/{request}/events', headers=headers, json={})
        row = (await client.get(prefix)).json()['turns'][-1]
        if case == 'repair':
            assert row['state'] == 'completed' and row['candidate']['command'] == 'seat.layout.create'
            assert len(attempts) == 2 and len(repairs) == 1
        elif case == 'exhausted':
            assert row['state'] == 'failed' and row['candidate'] is None and row['assistant_text'] is None
            assert 'message.delta' not in wire.text and len(attempts) == 2 and len(repairs) == 1
        else:
            assert row['state'] == 'completed' and row['assistant_text'] == FALSE_READY and row['candidate'] is None
            assert len(attempts) == 1 and repairs == []
        assert row['action_receipt'] is None
        assert query.classroom_read(auth, c, t, seating=True) is None


@pytest.mark.db
async def test_deferred_document_uses_answer_bound_not_tool_request_repr(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    body, calls = 'synthetic ' * 500, []
    def respond(messages, info):
        calls.append(True)
        assert len(calls) == 1, 'A validated candidate must not require another model response'
        return ModelResponse(parts=[ToolCallPart('prepare_document', {'action': 'create', 'title': '合成待核对文档', 'body': body})])
    sdk = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(respond))
    from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
    from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
    runtime = WorkspaceChatRuntime(WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0]),
        WorkspaceChatQueryGateway(business.identity, store, clock=lambda: clock[0]), sdk)
    thread, request = uuid4(), uuid4()
    runtime.business.send(auth, thread, request, '建立合成待核对文档，供我审核。')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    row = runtime.query.history(auth, thread)['turns'][-1]
    assert row['state'] == 'completed', sdk.last_failure_type
    assert row['candidate']['body'] == body and len(row['assistant_text']) < 100
    assert row['action_receipt'] is None and not query.documents(*auth, c, t)
    assert any(event.type == 'draft.available' for event in events) and len(calls) == 1


@pytest.mark.db
async def test_missing_exam_full_mark_pauses_for_information_not_an_invented_default(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    calls = []
    def respond(messages, info):
        calls.append(True)
        assert len(calls) <= 2, 'One model response per user turn; no invented full mark'
        return ModelResponse(parts=[ToolCallPart('prepare_exam', {'title': '合成缺信息月考', 'subject': '数学', 'maximum_score': '100'})])
    sdk = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(respond))
    app = create_workspace_chat_app(Settings(), worker=business, query=query, sdk=sdk)
    cookies = dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    prefix = f'/api/workspaces/{auth[3]}/workspace-chat/threads/{uuid4()}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8000', cookies=cookies) as client:
        request = uuid4()
        await client.post(prefix + '/turns', headers=headers, json={'request_id': str(request), 'text': '建立合成缺信息月考，科目数学。'})
        wire = await client.post(prefix + f'/turns/{request}/events', headers=headers, json={})
        row = (await client.get(prefix)).json()['turns'][-1]
        assert row['state'] == 'completed' and row['assistant_text'] == '这场考试的满分是多少？'
        assert row['candidate'] is None and row['action_receipt'] is None
        assert 'draft.available' not in wire.text and len(calls) == 1
        request = uuid4()
        await client.post(prefix + '/turns', headers=headers, json={'request_id': str(request), 'text': '满分100。'})
        await client.post(prefix + f'/turns/{request}/events', headers=headers, json={})
        row = (await client.get(prefix)).json()['turns'][-1]
    assert row['state'] == 'completed' and row['candidate']['command'] == 'exam.create'
    assert row['candidate']['maximum_score'] == '100' and row['action_receipt'] is None and len(calls) == 2
    assert query.classroom_read(auth, c, t)['exams'] == []
