"""Bounded, same-chat historical user quotes through real QG/PG and SDK."""
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.application.identity import IdentityDenied
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from class_os.application.workbench import WorkbenchQueryGateway
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.workbench import WorkbenchStore
from class_os.infrastructure.workspace_actions import WorkspaceActionCapture
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from test_workspace_chat_storage import workspace_chat, roster, identity


@pytest.fixture
def notes(workspace_chat):
    _, _, auth, old_owner, old_runtime, clock, old_store, boundary = workspace_chat
    owner = Database(old_owner.engine.url, migration=True, profile='classroom-work-d4')
    database = Database(old_runtime.engine.url, profile='classroom-work-d4')
    migrate(owner)
    store = WorkbenchStore(database, old_store.restrictions)
    business = WorkspaceChatBusinessGateway(boundary, store, clock=lambda: clock[0])
    query = WorkspaceChatQueryGateway(boundary, store, clock=lambda: clock[0])
    work = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    def save(thread, body, state='completed', answer='合成回复'):
        request = uuid4()
        business.send(auth, thread, request, body)
        ticket = business.claim(auth, thread, request)
        return business.finish(auth, ticket, state, answer if state == 'completed' else None)
    try:
        yield business, query, work, auth, owner, clock, store, boundary, save
    finally:
        owner.close(); database.close()


@pytest.mark.db
def test_literal_quotes_include_failed_notes_not_assistant_or_other_threads_and_clear(notes):
    business, query, _, auth, _, _, store, boundary, save = notes
    thread, other = uuid4(), uuid4()
    original = '前' * 700 + '合成作品核对：只是一条当时的笔记。' + '后' * 650
    save(thread, original, 'failed')
    for index in range(8):
        save(thread, f'合成后续闲聊{index}', answer='合成仅助手说的内容')
    save(other, '合成作品核对：另一个对话的不同内容')
    rebuilt = WorkspaceChatQueryGateway(boundary, store, clock=query.clock)
    result = rebuilt.recall(auth, thread, '合成作品核对', before=10)
    assert result['authority'] == 'historical-user-message' and not result['truncated']
    assert len(result['items']) == 1
    item = result['items'][0]
    assert item['ordinal'] == 1 and item['excerpt_truncated'] and item['recorded_at']
    assert item['quote'] == original[item['excerpt_start']:item['excerpt_start'] + 600]
    assert '合成作品核对' in item['quote'] and len(item['quote']) == 600
    assert not rebuilt.recall(auth, thread, '合成仅助手说的内容', before=10)['items']
    assert not rebuilt.recall(auth, thread, '合成作品核对', before=1)['items']
    assert not rebuilt.recall(auth, thread, '%_', before=10)['items']
    save(thread, '字面%_记号')
    assert len(rebuilt.recall(auth, thread, '%_', before=11)['items']) == 1
    for keyword, before in [('', 10), ('x', 10), ('a' * 81, 10), ('合成', True), ('合成', 0), ('合成', 10001)]:
        with pytest.raises(CommandRejected):
            rebuilt.recall(auth, thread, keyword, before=before)
    with pytest.raises(CommandRejected):
        rebuilt.recall(auth, uuid4(), '合成', before=10)
    with pytest.raises(IdentityDenied):
        rebuilt.recall((*auth[:3], uuid4()), thread, '合成', before=10)
    other_header = query.history(auth, other)['thread']
    business.control(auth, other, other_header['version'], 'archive')
    with pytest.raises(CommandRejected):
        rebuilt.recall(auth, other, '合成', before=10)
    header = query.history(auth, thread)['thread']
    business.control(auth, thread, header['version'], 'clear')
    with pytest.raises(CommandRejected):
        rebuilt.recall(auth, thread, '合成', before=10)
    assert all(row['user_text'] is None for row in query.history(auth, thread)['turns'])


@pytest.mark.db
async def test_sdk_recalls_beyond_history_window_without_class_or_business_writes(notes):
    business, query, work, auth, owner, _, _, _, save = notes
    thread = uuid4()
    note = '合成口述笔记：展板材料放在蓝色收纳盒。'
    save(thread, note)
    # More than both the six-turn SDK window and twenty-turn history page.
    for index in range(22):
        save(thread, f'合成闲聊{index}')
    seen = []
    def respond(messages, info):
        returned = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
        if not returned:
            assert not any(note in str(message) for message in messages)
            assert 'recall_this_chat' in {tool.name for tool in info.function_tools}
            return ModelResponse(parts=[ToolCallPart('recall_this_chat', {'keyword': '展板材料'})])
        value = returned[-1].content
        seen.append(value)
        assert value['items'][0]['quote'] == note and value['items'][0]['ordinal'] == 1
        return ModelResponse(parts=[TextPart('你在这段对话第1条笔记中说：展板材料放在蓝色收纳盒。')])
    runtime = WorkspaceChatRuntime(business, query, PydanticAgentRuntime(work, model_factory=lambda _: FunctionModel(respond)))
    request = uuid4()
    business.send(auth, thread, request, '之前我说展板材料放在哪里？')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    assert any(event.type == 'run.completed' for event in events), runtime.sdk.last_failure_type
    stored = query.turn(auth, thread, request)[1]
    assert stored['candidate'] is None and '蓝色收纳盒' in stored['assistant_text']
    assert len(seen) == 1 and [event async for event in runtime.stream_queued(auth, thread, request)] == []
    assert WorkspaceChatQueryGateway(query.identity, query.store, clock=query.clock).turn(auth, thread, request)[1]['assistant_text'] == stored['assistant_text']
    with owner.transaction(read_only=True) as connection:
        for table in ('school_class', 'student', 'record_revision', 'manual_task', 'working_document'):
            assert connection.execute(text(f'SELECT count(*) FROM class_os.{table}')).scalar_one() == 0


@pytest.mark.db
async def test_clear_during_recall_prevents_release_and_limit_is_honest(notes):
    business, query, work, auth, _, _, _, _, save = notes
    thread = uuid4()
    for index in range(7):
        save(thread, f'合成便签{index}')
    result = query.recall(auth, thread, '合成便签', before=8)
    assert result['truncated'] and [item['ordinal'] for item in result['items']] == [7, 6, 5, 4, 3]
    def respond(messages, info):
        returned = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
        if not returned:
            return ModelResponse(parts=[ToolCallPart('recall_this_chat', {'keyword': '合成便签'})])
        active = query.turn(auth, thread, request)[1]
        business.cancel(auth, thread, request, active['version'])
        header = query.history(auth, thread)['thread']
        business.control(auth, thread, header['version'], 'clear')
        return ModelResponse(parts=[TextPart('合成不应释放的旧笔记内容')])
    runtime = WorkspaceChatRuntime(business, query, PydanticAgentRuntime(work, model_factory=lambda _: FunctionModel(respond)))
    request = uuid4()
    business.send(auth, thread, request, '找合成便签')
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    assert not any(event.type in ('run.completed', 'message.delta', 'draft.available') for event in events)
    assert query.history(auth, thread)['thread']['status'] == 'cleared'


async def test_unbound_recall_is_unavailable_not_a_successful_empty_search():
    capture = WorkspaceActionCapture(('找以前的笔记',), classroom_enabled=True)
    tools = capture.tools(None, None, lambda: None, lambda *a, **k: None)
    recall = next(tool for tool in tools if tool.__name__ == 'recall_this_chat')
    assert (await recall('合成'))['status'] == 'unavailable'
    assert capture.proposed is None
    legacy = WorkspaceActionCapture(('普通聊天',)).tools(None, None, lambda: None, lambda *a, **k: None)
    assert not any(tool.__name__ == 'recall_this_chat' for tool in legacy)
