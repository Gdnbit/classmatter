"""Real SDK + HTTP + QG/BCG + PG; model provider is explicitly synthetic."""
from uuid import uuid4

import httpx
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart, RetryPromptPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.workbench import WorkbenchBusinessGateway, WorkbenchQueryGateway
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from test_workspace_chat_storage import workspace_chat, roster, identity


@pytest.mark.db
async def test_persistence_failure_is_distinct_from_model_success(workspace_chat, monkeypatch):
    business, history, auth, _, _, clock, store, boundary = workspace_chat
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    reports = []
    sdk = PydanticAgentRuntime(query, diagnostics=reports.append,
        model_factory=lambda _: FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart('Hello')])))
    runtime = WorkspaceChatRuntime(business, history, sdk)
    thread, request = uuid4(), uuid4()
    business.send(auth, thread, request, 'Hello')
    original = business.finish
    def fail_completed(credentials, ticket, state, *args, **kwargs):
        if state == 'completed':
            raise RuntimeError('private persistence detail')
        return original(credentials, ticket, state, *args, **kwargs)
    monkeypatch.setattr(business, 'finish', fail_completed)
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    assert not any(event.type in ('run.completed', 'message.delta', 'draft.available') for event in events)
    assert history.history(auth, thread)['turns'][0]['state'] == 'unknown'
    assert [report['outcome'] for report in reports] == ['completed', 'failed']
    assert reports[-1]['phase'] == 'persistence_finish'
    assert reports[-1]['run_id'] == str(request)


@pytest.mark.db
async def test_multistep_uses_receipts_and_current_reads_across_restarted_runtimes(workspace_chat):
    business, history, auth, owner, _, clock, store, boundary = workspace_chat
    commands = WorkbenchBusinessGateway(boundary, store, clock=lambda: clock[0])
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    progress_seen, tools_seen, repairs = [], [], []
    original = '建立合成流程班，合成流程学期，2026-09-01至2027-01-30；然后添加合成流程学生，再建立文档合成流程小结。'
    def factory(request):
        completed = set()
        def respond(messages, info):
            assert not {'commit', 'approve', 'sql'} & {tool.name for tool in info.function_tools}
            if any(isinstance(part, RetryPromptPart) for part in messages[-1].parts):
                repairs.append(True)
                return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
            returned = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
            if not returned:
                return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
            tool, value = returned[-1].tool_name, returned[-1].content
            tools_seen.append(tool)
            if tool == 'read_task_progress':
                progress_seen.append(value)
                assert original in value['requests']
                if any(action['status'] == 'awaiting-confirmation' for action in value['actions']):
                    return ModelResponse(parts=[TextPart('请先确认尚未保存的步骤。')])
                completed.update(action['command'] for action in value['actions'] if action['status'] == 'committed')
                if 'class.create' not in completed:
                    return ModelResponse(parts=[ToolCallPart('prepare_class_create', {'name': '合成流程班', 'term_name': '合成流程学期', 'start_date': '2026-09-01', 'end_date': '2027-01-30'})])
                if 'document.create' in completed:
                    if repairs:
                        assert len(value['actions']) == 3 and all(action['status'] == 'committed' for action in value['actions'])
                        return ModelResponse(parts=[TextPart('根据已保存的回执，班级、学生与文档三步均已完成，没有重复创建。')])
                    return ModelResponse(parts=[TextPart('已完成三步，没有重复创建。')])
                return ModelResponse(parts=[ToolCallPart('read_class_work', {'kind': 'class'})])
            if tool == 'read_class_work':
                # Exercise a real SDK loop longer than the former 3-tool limit.
                kinds = [part.args_as_dict().get('kind') for message in messages for part in message.parts
                         if isinstance(part, ToolCallPart) and part.tool_name == 'read_class_work']
                if len(kinds) < 4:
                    return ModelResponse(parts=[ToolCallPart('read_class_work', {'kind': ['class', 'students', 'tasks', 'documents'][len(kinds)]})])
                if 'student.create' not in completed:
                    return ModelResponse(parts=[ToolCallPart('prepare_student', {'action': 'create', 'name': '合成流程学生'})])
                return ModelResponse(parts=[ToolCallPart('prepare_document', {'action': 'create', 'title': '合成流程小结', 'body': '待核对的小结。'})])
            return ModelResponse(parts=[TextPart('已准备下一步，请核对确认。')])
        return FunctionModel(respond)
    thread = uuid4()
    for index, expected in enumerate(['class.create', None, 'student.create', 'document.create', None]):
        # Recreate SDK/runtime every time: progress must come from PG receipts, not RAM.
        runtime = WorkspaceChatRuntime(business, history, PydanticAgentRuntime(query, model_factory=factory))
        key = uuid4()
        business.send(auth, thread, key, original if index == 0 else '继续完成上面的任务，只处理尚未完成的步骤。')
        events = [event async for event in runtime.stream_queued(auth, thread, key)]
        assert any(event.type == 'run.completed' for event in events), runtime.sdk.last_failure_type
        row = history.history(auth, thread)['turns'][-1]
        if expected is None:
            assert row['candidate'] is None
        else:
            assert row['candidate']['command'] == expected
        if index in (1, 2, 3):
            candidate_row = history.history(auth, thread)['turns'][0] if index == 1 else row
            from class_os.domain.workspace_chat import candidate
            proposal = commands.preview(*auth, candidate(candidate_row['candidate']))
            approval = commands.approve(*auth, proposal.proposal_id, proposal.payload_hash) if proposal.risk == 'W2' else None
            commands.commit(*auth, proposal.proposal_id, uuid4(), approval)
        # Refresh/repeated dispatch never repeats a tool or business operation.
        assert [event async for event in runtime.stream_queued(auth, thread, key)] == []
    assert len(progress_seen) == 6 and repairs == [True] and tools_seen.count('read_class_work') == 8
    assert [action['status'] for action in progress_seen[1]['actions']] == ['awaiting-confirmation']
    assert [action['status'] for action in progress_seen[-1]['actions']] == ['committed'] * 3
    with owner.transaction(read_only=True) as connection:
        for table in ('school_class', 'student', 'working_document'):
            assert connection.execute(text(f'SELECT count(*) FROM class_os.{table}')).scalar_one() == 1


@pytest.mark.db
@pytest.mark.parametrize('false_ready', [False, True])
async def test_conversation_creates_and_edits_core_objects_after_human_confirmation(workspace_chat, false_ready):
    business, history, credentials, owner, _, clock, store, boundary = workspace_chat
    commands = WorkbenchBusinessGateway(boundary, store, clock=lambda: clock[0])
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    current_tool, calls, histories = [None], [], []
    def model_factory(request):
        def respond(messages, info):
            assert not {"commands_commit", "approve", "sql"} & {tool.name for tool in info.function_tools}
            returned = any(isinstance(part, ToolReturnPart) for part in messages[-1].parts)
            if returned:
                if any(isinstance(part, ToolReturnPart) and part.tool_name == "read_class_work" for part in messages[-1].parts):
                    return ModelResponse(parts=[ToolCallPart(*current_tool[0])])
                return ModelResponse(parts=[TextPart("合成候选已准备，请在对话中预览确认；尚未保存。")])
            repair = any(isinstance(part, RetryPromptPart) for part in messages[-1].parts)
            if not repair:
                calls.append(request.text); histories.append(len(messages))
                if false_ready:
                    return ModelResponse(parts=[TextPart("已为你准备好这项修改，请确认保存。")])
            if current_tool[0][0] == "prepare_document" and current_tool[0][1]["action"] == "edit":
                return ModelResponse(parts=[ToolCallPart("read_class_work", {"kind": "documents", "search": current_tool[0][1]["title"]})])
            return ModelResponse(parts=[ToolCallPart(*current_tool[0])])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=model_factory)
    app = create_workspace_chat_app(Settings(), worker=commands, query=query, sdk=sdk)
    cookies = dict(zip(("class_os_session", "class_os_client", "class_os_csrf"), credentials[:3]))
    headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": credentials[2]}
    base = f"/api/workspaces/{credentials[3]}"
    thread = uuid4()
    steps = [
        ("建立合成七一班，合成第一学期，2026-09-01至2027-01-30", "prepare_class_create", {"name": "合成七一班", "term_name": "合成第一学期", "start_date": "2026-09-01", "end_date": "2027-01-30"}, "class.create"),
        ("把班名改为合成七二班", "prepare_class_edit", {"name": "合成七二班"}, "class.update"),
        ("学期名称更正为合成修订学期", "prepare_term_edit", {"name": "合成修订学期"}, "term.update"),
        ("添加合成学生甲", "prepare_student", {"action": "create", "name": "合成学生甲"}, "student.create"),
        ("将合成学生甲改名为合成学生乙", "prepare_student", {"action": "rename", "name": "合成学生甲", "new_name": "合成学生乙"}, "student.update_name"),
        ("建立任务合成收集回执", "prepare_task", {"action": "create", "title": "合成收集回执"}, "task.create"),
        ("把任务合成收集回执改为合成收集签字回执", "prepare_task", {"action": "edit", "title": "合成收集回执", "new_title": "合成收集签字回执"}, "task.update"),
        ("生成文档合成班级小结", "prepare_document", {"action": "create", "title": "合成班级小结", "body": "合成小结，待核对"}, "document.create"),
        ("修改文档合成班级小结，更新正文", "prepare_document", {"action": "edit", "title": "合成班级小结", "body": "合成更新正文，仍为工作草稿"}, "document.revise"),
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://127.0.0.1:8000", cookies=cookies) as client:
        capabilities = await client.get(base + "/workspace-chat/capabilities")
        assert capabilities.status_code == 200 and capabilities.json()["class_required"] is False
        for index, (message, tool, args, command) in enumerate(steps):
            current_tool[0] = (tool, args)
            key = uuid4(); path = base + f"/workspace-chat/threads/{thread}/turns/{key}"
            sent = await client.post(base + f"/workspace-chat/threads/{thread}/turns", headers=headers, json={"request_id": str(key), "text": message})
            assert sent.status_code == 200, sent.text
            assert len(calls) == index  # Persistence and GET do not call the model.
            saved = await client.get(base + f"/workspace-chat/threads/{thread}")
            assert saved.status_code == 200 and saved.json()["turns"][-1]["state"] == "queued"
            stream = await client.post(path + "/events", headers=headers, json={})
            assert stream.status_code == 200 and "event: run.completed" in stream.text, (sdk.last_failure_type, stream.text)
            saved = await client.get(base + f"/workspace-chat/threads/{thread}")
            turn = saved.json()["turns"][-1]
            assert turn["state"] == "completed" and turn["candidate"]["command"] == command, turn
            assert len(calls) == index + 1
            # Repeated start is a no-op, not another model run or write.
            assert (await client.post(path + "/events", headers=headers, json={})).text == ""
            assert len(calls) == index + 1
            if index == 0:
                assert query.context(*credentials) is None
                wrong = await client.post(path + "/proposal", headers=headers, json={"candidate_hash": "0" * 64})
                assert wrong.status_code == 409
            proposed = await client.post(path + "/proposal", headers=headers, json={"candidate_hash": turn["candidate_hash"]})
            assert proposed.status_code == 200, proposed.text
            preview = proposed.json()
            approval = None
            if preview["risk"] == "W2":
                approved = await client.post(base + "/commands/approve", headers=headers,
                    json={"proposal_id": preview["proposal_id"], "payload_hash": preview["payload_hash"]})
                assert approved.status_code == 200, approved.text
                approval = approved.json()["approval"]
            commit = {"proposal_id": preview["proposal_id"], "idempotency_key": str(uuid4()), "approval": approval}
            receipt = await client.post(base + "/commands/commit", headers=headers, json=commit)
            assert receipt.status_code == 200, receipt.text
            repeated = await client.post(base + "/commands/commit", headers=headers, json=commit)
            assert repeated.status_code == 200 and repeated.json() == receipt.json()
    assert histories[-1] > histories[0]
    current = query.context(*credentials)
    assert current.name == "合成七二班"
    assert [row.name for row in query.roster(*credentials, current.class_id, current.term_id)] == ["合成学生乙"]
    assert query.projection(*credentials, current.class_id, current.term_id)["tasks"][0]["title"] == "合成收集签字回执"
    documents = query.documents(*credentials, current.class_id, current.term_id)
    document = query.document(*credentials, current.class_id, current.term_id, documents[0]["document_id"])
    assert document["version"] == 2 and document["body"] == "合成更新正文，仍为工作草稿"
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.workspace_chat_turn WHERE state='completed'")).scalar_one() == 9
        assert connection.execute(text("SELECT count(*) FROM class_os.working_document_revision")).scalar_one() == 2


@pytest.mark.db
async def test_ordinary_chat_reads_no_class_and_failed_output_persistence_releases_no_answer(workspace_chat, monkeypatch):
    business, history, auth, _, _, clock, store, boundary = workspace_chat
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    def forbidden(*args):
        raise AssertionError('Ordinary chat must not fetch classes')
    monkeypatch.setattr(query, 'history', forbidden)
    calls = []
    def factory(request):
        def respond(messages, info):
            calls.append(request.text)
            return ModelResponse(parts=[TextPart('合成普通回答')])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory)
    runtime = WorkspaceChatRuntime(business, history, sdk)
    thread, key = uuid4(), uuid4()
    business.send(auth, thread, key, '合成普通聊天')
    original = business.finish
    def unavailable(*args, **kwargs):
        raise RuntimeError('Synthetic persistence failure')
    monkeypatch.setattr(business, 'finish', unavailable)
    events = [event async for event in runtime.stream_queued(auth, thread, key)]
    assert not any(event.type in ('message.delta', 'run.completed', 'draft.available') for event in events)
    assert len(calls) == 1
    assert [event async for event in runtime.stream_queued(auth, thread, key)] == []
    monkeypatch.setattr(business, 'finish', original)
    row = history.history(auth, thread)['turns'][0]
    assert row['state'] == 'running' and row['assistant_text'] is None
    business.cancel(auth, thread, key, row['version'])
    assert history.history(auth, thread)['turns'][0]['state'] == 'cancelled'


@pytest.mark.db
async def test_missing_class_dates_remain_conversational_not_invented_data(workspace_chat):
    business, history, auth, owner, _, clock, store, boundary = workspace_chat
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    def factory(request):
        def respond(messages, info):
            if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
                assert any('needs-information' in str(part.content) for part in messages[-1].parts if isinstance(part, ToolReturnPart))
                return ModelResponse(parts=[TextPart('请告诉我这个学期的开始和结束日期。')])
            return ModelResponse(parts=[ToolCallPart('prepare_class_create', {'name': '合成班', 'term_name': '合成学期', 'start_date': '2026-09-01', 'end_date': '2027-01-30'})])
        return FunctionModel(respond)
    runtime = WorkspaceChatRuntime(business, history, PydanticAgentRuntime(query, model_factory=factory))
    thread, key = uuid4(), uuid4()
    business.send(auth, thread, key, '建立合成班，合成学期')
    events = [event async for event in runtime.stream_queued(auth, thread, key)]
    assert any(event.type == 'run.completed' for event in events)
    row = history.history(auth, thread)['turns'][0]
    assert row['candidate'] is None and '日期' in row['assistant_text']
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.school_class')).scalar_one() == 0


@pytest.mark.db
async def test_repeating_multistep_tools_exhausts_budget_without_writes(workspace_chat):
    business, history, auth, owner, _, clock, store, boundary = workspace_chat
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    calls = []
    def respond(messages, info):
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
    diagnostics = []
    sdk = PydanticAgentRuntime(query, model_factory=lambda _: FunctionModel(respond), diagnostics=diagnostics.append)
    runtime = WorkspaceChatRuntime(business, history, sdk)
    thread, request = uuid4(), uuid4()
    business.send(auth, thread, request, '合成循环故障，不应无限执行。')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    assert not any(event.type in ('message.delta', 'draft.available', 'run.completed') for event in events)
    row = history.history(auth, thread)['turns'][0]
    assert row['state'] == 'failed' and row['candidate'] is None and row['assistant_text'] is None
    assert 1 < len(calls) <= 10 and sdk.active == 0
    assert len(diagnostics) == 1
    assert diagnostics[0]['run_id'] == str(request)
    assert diagnostics[0]['category'] == 'local_usage_limit'
    assert diagnostics[0]['model_requests'] == len(calls)
    assert [event async for event in runtime.stream_queued(auth, thread, request)] == []
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.school_class')).scalar_one() == 0
