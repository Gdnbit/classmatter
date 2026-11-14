"""Public-source retrieval boundaries and actual SDK/PG conversation round trips."""
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.identity import IdentityDenied
from class_os.application.policy_knowledge import PASSAGES, search_policy, policy_answer, requires_policy_search
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from test_chat_note_recall import notes, workspace_chat, roster, identity


@pytest.mark.parametrize('question,expected', [
    ('你好', False), ('今天进校园活动很累', False),
    ('帮我查宁乡教师减负规定', True), ('宁乡某校报销上限是多少？', True),
])
def test_evidence_prerequisite_does_not_route_ordinary_chat(question, expected):
    assert requires_policy_search(question) is expected


@pytest.mark.parametrize('question,expected', [
    ('宁乡县初中老师被安排很多与教学无关的进校园活动，有什么减负依据？', '第15条'),
    ('宁乡小学能在家长群发布成绩排名吗？', '第17条'),
    ('长沙初中晚自习能不能纳入课后服务？', '服务范围'),
    ('长沙民办小学课后服务是否自愿？', '自主自愿'),
    ('法院类似案例可以直接作为裁判依据吗？', '第二十一条'),
])
def test_search_locates_reviewed_passage_with_precise_source(question, expected):
    result = search_policy(question)
    assert result['matches'] and any(expected in item['locator'] for item in result['matches'])
    for item in result['matches']:
        assert item['quote'] and item['url'].startswith('https://') and len(item['snapshot_sha256']) == 64
        assert item['validity'] == 'not_verified' and item['applicability'] == 'candidate_only'
    assert not result['school_rules_available']


@pytest.mark.parametrize('question', [
    '宁乡一中本学期办公室内部报销上限是多少？',
    '宁乡幼儿园的课后服务依据是什么？',
    '山东小学课后服务是否必须参加？',
    '湖南岳阳小学的课后服务要求是什么？',
    '宁乡公办小学办公室报销标准是多少？',
    '宁乡中职能按长沙义务教育课后服务办法安排晚自习吗？',
])
def test_missing_school_rules_and_out_of_scope_never_get_false_basis(question):
    result = search_policy(question)
    assert not result['matches']
    answer = policy_answer('模型虚构的学校规定：已核实。', result)
    assert '没有找到' in answer and '学校规定：已核实' not in answer
    assert '缺少资料不代表不存在' in answer


@pytest.mark.parametrize('question', ['', ' ', None, ['课后服务'], 'x' * 2001])
def test_policy_search_rejects_invalid_input(question):
    with pytest.raises(ValueError):
        search_policy(question)


def test_citation_appendix_is_code_owned_and_bounded():
    result = search_policy('宁乡初中进校园活动减负')
    answer = policy_answer('已收录文件的相关条款如下 [P1]。', result)
    assert PASSAGES[0].quote in answer and PASSAGES[0].source.url in answer
    assert '现行效力尚待复核' in answer and '内部制度尚未收录' in answer
    for invalid in ('伪造依据[P999]', '伪造网址 https://example.com/fake-law', 'x' * 4000):
        with pytest.raises(ValueError):
            policy_answer(invalid, result)


@pytest.mark.db
async def test_policy_tool_without_class_persists_exact_evidence_and_no_business_change(notes):
    business, query, work, auth, owner, _, _, _, _ = notes
    question = '宁乡县初中进校园活动有什么减负依据？'
    tables = ('school_class', 'student', 'manual_task', 'command_proposal', 'command_receipt')
    with owner.transaction(read_only=True) as connection:
        before = {table: connection.execute(text(f'SELECT count(*) FROM class_os.{table}')).scalar_one() for table in tables}
    seen = []
    def respond(messages, info):
        returned = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
        if not returned:
            assert 'search_policy_knowledge' in {t.name for t in info.function_tools}
            return ModelResponse(parts=[ToolCallPart('search_policy_knowledge', {})])
        seen.append(returned[-1].content)
        return ModelResponse(parts=[TextPart('已收录文件第15条涉及进校园活动和教师减负 [P1]。')])
    runtime = WorkspaceChatRuntime(business, query, PydanticAgentRuntime(work, model_factory=lambda _: FunctionModel(respond)))
    thread, request = uuid4(), uuid4()
    business.send(auth, thread, request, question)
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    assert events[-1].type == 'run.completed'
    assert not any(event.type == 'draft.available' for event in events)
    answer = next(e.payload['text'] for e in events if e.type == 'message.delta')
    assert PASSAGES[0].quote in answer and PASSAGES[0].source.url in answer
    # New QG object/re-read uses persisted answer, not SDK memory or current corpus.
    fresh = type(query)(query.identity, query.store, clock=query.clock)
    row = fresh.history(auth, thread)['turns'][0]
    assert row['assistant_text'] == answer and row['candidate'] is row['action_receipt'] is None
    assert list([e async for e in runtime.stream_queued(auth, thread, request)]) == []
    assert len(seen) == 1
    with owner.transaction(read_only=True) as connection:
        for table in tables:
            # Fixed test-owned identifiers, not user/Agent SQL.
            assert connection.execute(text(f'SELECT count(*) FROM class_os.{table}')).scalar_one() == before[table]
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='class.context' AND class_id IS NULL")).scalar_one() >= 1
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='agent.run.completed'")).scalar_one() == 1
    with pytest.raises(IdentityDenied):
        work.policy_search(*auth[:3], uuid4(), question)


@pytest.mark.db
async def test_missing_evidence_cannot_be_replaced_with_model_prose(notes):
    business, query, work, auth, _, _, _, _, _ = notes
    def respond(messages, info):
        if not any(isinstance(p, ToolReturnPart) for p in messages[-1].parts):
            return ModelResponse(parts=[ToolCallPart('search_policy_knowledge', {})])
        return ModelResponse(parts=[TextPart('已确认该校报销上限为虚构金额。')])
    runtime = WorkspaceChatRuntime(business, query, PydanticAgentRuntime(work, model_factory=lambda _: FunctionModel(respond)))
    thread, request = uuid4(), uuid4()
    business.send(auth, thread, request, '宁乡一中办公室报销上限是多少？')
    events = [e async for e in runtime.stream_queued(auth, thread, request)]
    assert events[-1].type == 'run.completed'
    answer = query.history(auth, thread)['turns'][0]['assistant_text']
    assert '没有找到' in answer and '虚构金额' not in answer


@pytest.mark.db
async def test_policy_read_failure_preserves_user_text_without_answer_or_draft(notes, monkeypatch):
    business, query, work, auth, _, _, _, _, _ = notes
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart('search_policy_knowledge', {})])
    def unavailable(*args):
        raise RuntimeError('Synthetic source boundary outage')
    monkeypatch.setattr(work, 'policy_search', unavailable)
    runtime = WorkspaceChatRuntime(business, query, PydanticAgentRuntime(work, model_factory=lambda _: FunctionModel(respond)))
    thread, request = uuid4(), uuid4()
    question = '宁乡小学进校园减负依据'
    business.send(auth, thread, request, question)
    events = [e async for e in runtime.stream_queued(auth, thread, request)]
    assert events[-1].type == 'run.failed'
    row = query.history(auth, thread)['turns'][0]
    assert row['user_text'] == question and row['assistant_text'] is row['candidate'] is None


@pytest.mark.db
@pytest.mark.parametrize('fault', ['bad_citation', 'missing_read'])
async def test_sdk_repairs_fabricated_citation_before_release(notes, fault):
    business, query, work, auth, _, _, _, _, _ = notes
    calls = []
    def respond(messages, info):
        calls.append(True)
        if fault == 'missing_read' and len(calls) == 1:
            return ModelResponse(parts=[TextPart('模型凭记忆编造的宁乡规定。')])
        if fault == 'missing_read' and len(calls) == 2:
            return ModelResponse(parts=[ToolCallPart('search_policy_knowledge', {})])
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart('search_policy_knowledge', {})])
        return ModelResponse(parts=[TextPart('伪造引用[P999]' if len(calls) == 2 else '已收录的进校园规定可供核对[P1]。')])
    runtime = WorkspaceChatRuntime(business, query, PydanticAgentRuntime(work, model_factory=lambda _: FunctionModel(respond)))
    thread, request = uuid4(), uuid4()
    business.send(auth, thread, request, '宁乡初中进校园活动减负依据')
    events = [e async for e in runtime.stream_queued(auth, thread, request)]
    assert events[-1].type == 'run.completed' and len(calls) == 3
    assert '[P999]' not in query.history(auth, thread)['turns'][0]['assistant_text']
