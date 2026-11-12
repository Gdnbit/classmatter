"""No prose-only preview for supported operations; isolated synthetic fixtures."""
from uuid import uuid4
import httpx
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from class_os.infrastructure.action_output import unbacked_action_promise
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity

PROMISE = '已为你准备好这项修改，请核对并确认保存。'


@pytest.mark.parametrize('answer', ['已记录“班长正在收集”这一事实，并将“合成作品核对”任务暂时搁置。请确认是否继续下一步操作。', '已完成合成作品核对任务。', '已结束这项跟进。', '已取消合成作品核对任务。'])
def test_workflow_claims_cannot_replace_actual_candidates(answer):
    assert unbacked_action_promise(answer, '合成作品核对先等待，跟进记录原文为“班长正在收集”')
    assert not unbacked_action_promise(answer, '仅讨论这句话，不执行任何操作。')


@pytest.mark.db
@pytest.mark.parametrize('mistake,keeps_failing', [('prose', False), ('create', False), ('create', True), ('missing-note', False), ('short-note', False), ('missing-note', True)])
async def test_waiting_note_false_saved_reply_repairs_to_the_original_task_candidate(classroom_work, mistake, keeps_failing):
    from class_os.domain.activity import CreateTask
    from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
    from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
    business, query, auth, _, clock, store, commit, c, t, _ = classroom_work
    task = CreateTask('task.create', uuid4(), c, t, '合成作品核对', None, None, None)
    commit(task)
    calls = []
    def respond(messages, info):
        calls.append(True)
        if not keeps_failing and any(isinstance(part, RetryPromptPart) for part in messages[-1].parts):
            return ModelResponse(parts=[ToolCallPart('prepare_task', {'action': 'edit', 'title': '合成作品核对', 'status': 'waiting', 'evidence': '班长正在收集'})])
        part = (TextPart('已记录“班长正在收集”这一事实，并将“合成作品核对”任务暂时搁置。请确认是否继续下一步操作。') if mistake == 'prose' else
            ToolCallPart('prepare_task', {'action': 'create' if mistake == 'create' else 'edit', 'title': '合成作品核对', 'status': 'waiting', 'evidence': '' if mistake == 'missing-note' else '班长' if mistake == 'short-note' else '班长正在收集'}))
        return ModelResponse(parts=[part])
    sdk = PydanticAgentRuntime(query, timeout=45, model_factory=lambda _: FunctionModel(respond))
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    runtime = WorkspaceChatRuntime(chats, history, sdk)
    thread, request = uuid4(), uuid4()
    chats.send(auth, thread, request, '合成作品核对先等待，跟进记录原文为“班长正在收集”')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    row = history.turn(auth, thread, request)[1]
    assert len(calls) == 2 and row['action_receipt'] is None
    if keeps_failing:
        assert row['state'] == 'failed' and row['candidate'] is row['assistant_text'] is None
        assert not any(event.type in ('message.delta', 'draft.available') for event in events)
    else:
        assert row['state'] == 'completed' and row['candidate']['command'] == 'task.update' and row['candidate']['status'] == 'waiting'
        assert row['candidate']['evidence'] == '班长正在收集'
    current = query.projection(*auth, c, t)
    assert not current['records'] and len(current['tasks']) == 1 and current['tasks'][0]['version'] == 1
    assert any(event.type == 'draft.available' for event in events) is not keeps_failing


@pytest.mark.parametrize('message', ['创建班级合成班', '学期更正为合成学期', '添加学生合成甲', '把班名改为合成班',
    '建立任务合成回执', '编辑文档合成小结', '建立合成月考数学，满分100', '录入合成甲成绩80', '安排合成甲座位', '交换两位学生座位', '生成预览'])
def test_action_promises_require_candidates(message):
    assert unbacked_action_promise(PROMISE, message, ('创建任务合成回执', message))
    assert unbacked_action_promise('已保存任务。', message, ('创建任务合成回执', message))


@pytest.mark.parametrize('message', ['你好', '谢谢', '翻译：已创建任务，请确认', '仅讨论文档，不执行操作',
    '假设创建班级要怎么做？', '不要修改成绩', '写一个笑话'])
def test_chat_and_discussion_do_not_force_business_tools(message):
    assert not unbacked_action_promise(PROMISE, message, (message,))


def test_followup_and_rejected_tool_are_not_false_success():
    assert unbacked_action_promise(PROMISE, '满分100', ('建立考试合成月考', '满分100'))
    assert unbacked_action_promise(PROMISE, '是', ('创建任务合成回执', '是'))
    assert unbacked_action_promise(PROMISE, '合成甲', ('合成甲',), attempted=True)
    assert not unbacked_action_promise('请告诉我文档标题。', '创建文档', ('创建文档',))
    assert unbacked_action_promise(PROMISE, '建立合成月考数学，满分100', ('建立合成月考数学，满分100',))
    assert not unbacked_action_promise('已保存的任务包括合成回执，无需重复建立。', '创建任务合成回执', ('创建任务合成回执',))
    message = '显示上次待确认的预览'
    text = '上次任务已准备好，请在上方核对确认。'
    assert unbacked_action_promise(text, message, ('创建任务合成回执', message))
    assert not unbacked_action_promise(text, message, ('创建任务合成回执', message), pending=True)


@pytest.mark.parametrize('text', ['已生成文档，请点击预览。', '任务准备好了，请确认。', '方案已就绪，请核对。', 'The task is ready for review.'])
def test_ready_wording_does_not_replace_an_actual_candidate(text):
    assert unbacked_action_promise(text, '创建任务合成回执', ('创建任务合成回执',))


@pytest.mark.parametrize('message', ['创建文档合成小结，先不要保存', '创建任务合成回执，不用自动提交', '三行五列，暂不保存'])
def test_withholding_commit_still_requires_the_promised_preview(message):
    assert unbacked_action_promise('已准备好座位或文档，请核对确认。', message, (message,))


@pytest.mark.db
async def test_rejected_preparations_ask_only_missing_information_without_model_false_ready(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    selected, calls = [None], []
    def respond(messages, info):
        calls.append(True)
        if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
            pytest.fail('Known clarification must not request a false-ready model response')
        return ModelResponse(parts=[ToolCallPart(*selected[0])])
    sdk = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(respond))
    app = create_workspace_chat_app(Settings(), worker=business, query=query, sdk=sdk)
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    cookies = dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))
    cases = [
        ('修改班级名称', 'prepare_class_edit', {'name': '未提供的新班名'}, '班级要改成什么名称？'),
        ('修改学期名称', 'prepare_term_edit', {'name': '未提供的新学期'}, '请明确要更正的学期名称或日期。'),
        ('把合成学生0改名', 'prepare_student', {'action': 'rename', 'name': '合成学生0', 'new_name': '未提供的新名字'}, '学生的新姓名是什么？'),
        ('添加合成学生0', 'prepare_student', {'action': 'create', 'name': '合成学生0'}, '班里已有这个姓名，是同一位学生吗？'),
        ('创建任务', 'prepare_task', {'action': 'create', 'title': '未提供的任务'}, '要处理哪项任务？'),
        ('编辑不存在的任务', 'prepare_task', {'action': 'edit', 'title': '不存在的任务', 'new_title': ''}, '没有找到唯一的未完成任务，请确认标题。'),
        ('创建文档', 'prepare_document', {'action': 'create', 'title': '未提供的文档', 'body': '合成正文'}, '要处理哪份文档？'),
        ('编辑不存在的文档', 'prepare_document', {'action': 'edit', 'title': '不存在的文档', 'body': '合成正文'}, '没有找到唯一的可编辑文档，请确认标题。'),
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:8000', cookies=cookies) as client:
        for index, (text, tool, args, question) in enumerate(cases):
            selected[0] = tool, args
            prefix = f'/api/workspaces/{auth[3]}/workspace-chat/threads/{uuid4()}'
            request = uuid4()
            assert (await client.post(prefix+'/turns', headers=headers, json={'request_id': str(request), 'text': text})).status_code == 200
            wire = await client.post(prefix+f'/turns/{request}/events', headers=headers, json={})
            row = (await client.get(prefix)).json()['turns'][-1]
            assert row['state'] == 'completed' and row['assistant_text'] == question, sdk.last_failure_type
            assert row['candidate'] is None and row['action_receipt'] is None and 'draft.available' not in wire.text
            assert len(calls) == index + 1
    assert query.context(*auth).name == '合成成绩班'
    assert [row.name for row in query.roster(*auth, c, t)] == ['合成学生0', '合成学生1']
    assert not query.documents(*auth, c, t) and not query.projection(*auth, c, t)['tasks']


@pytest.mark.db
async def test_generic_repair_is_bounded_and_can_refer_to_real_pending_card(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    calls = []
    def factory(request):
        def respond(messages, info):
            calls.append(request.text)
            if request.text == '创建任务合成耗尽':
                return ModelResponse(parts=[TextPart(PROMISE)])
            if request.text == '显示上次待确认的预览':
                if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
                    return ModelResponse(parts=[TextPart('上次任务已准备好，请在上方核对确认。')])
                return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
            if any(isinstance(part, RetryPromptPart) for part in messages[-1].parts):
                return ModelResponse(parts=[ToolCallPart('prepare_task', {'action': 'create', 'title': '合成待确认'})])
            return ModelResponse(parts=[TextPart(PROMISE)])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory)
    app = create_workspace_chat_app(Settings(), worker=business, query=query, sdk=sdk)
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    cookies = dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))
    prefix = f'/api/workspaces/{auth[3]}/workspace-chat/threads/{uuid4()}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:8000', cookies=cookies) as client:
        for message in ('创建任务合成耗尽', '创建任务合成待确认，先不要保存', '显示上次待确认的预览'):
            request = uuid4()
            await client.post(prefix+'/turns', headers=headers, json={'request_id': str(request), 'text': message})
            wire = await client.post(prefix+f'/turns/{request}/events', headers=headers, json={})
            rows = (await client.get(prefix)).json()['turns']
            row = rows[-1]
            assert row['action_receipt'] is None and not query.projection(*auth, c, t)['tasks']
            if message.endswith('耗尽'):
                assert row['state'] == 'failed' and row['assistant_text'] is None and row['candidate'] is None
                assert 'message.delta' not in wire.text and calls.count(message) == 2
            elif message.startswith('创建'):
                assert row['candidate']['command'] == 'task.create' and calls.count(message) == 2
            else:
                assert row['state'] == 'completed' and row['candidate'] is None and '上次任务' in row['assistant_text']
                assert rows[-2]['candidate']['command'] == 'task.create' and calls.count(message) == 2
