"""Real SDK, QG/BCG and isolated PG. FunctionModel is not a live-model score."""
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart, RetryPromptPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from class_os.domain.activity import CreateRecord, CreateTask, ChangeTask
from class_os.domain.personal_summary import TITLE, SUMMARY_TITLE, SummaryDelegation
from class_os.domain.workspace_chat import candidate
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from class_os.infrastructure.personal_summary_runtime import PersonalSummaryService
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


def assembly(fixture, *, before_prepare=None, fail=False, quiet=False, plain_question=False, premature_answer=False):
    business, query, auth, owner, clock, store, commit, c, t, students = fixture
    calls = []
    def factory(request):
        def respond(messages, info):
            calls.append(request.text)
            if fail and request.text.startswith('依据已确认'):
                raise TimeoutError('synthetic provider timeout')
            if '持续整理' in request.text and not request.text.startswith('依据已确认'):
                return ModelResponse(parts=[ToolCallPart('prepare_summary_delegation', {'quote': request.text,
                    'required_material': '班会主题' if '班会主题' in request.text else None})])
            if request.text.startswith('以后用三条'):
                return ModelResponse(parts=[ToolCallPart('prepare_summary_delegation', {'quote': request.text,
                    'action': 'update', 'style': 'three-points'})])
            if request.text.startswith('暂停'):
                return ModelResponse(parts=[ToolCallPart('prepare_summary_delegation', {'quote': request.text, 'action': 'pause'})])
            if request.text.startswith('这次') or request.text == '是':
                return ModelResponse(parts=[TextPart('好的。')])
            # Read only this run's tool returns; prior chat prose is not evidence.
            last_user = max(index for index, message in enumerate(messages)
                            if any(isinstance(part, UserPromptPart) for part in message.parts))
            if len(info.function_tools) == 1 and info.function_tools[0].name == 'read_task_progress':
                return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
            if premature_answer and request.text.startswith('班会主题是') and not any(isinstance(part, ToolReturnPart)
                    and part.tool_name == 'prepare_document' for message in messages[last_user:] for part in message.parts):
                return ModelResponse(parts=[ToolCallPart('prepare_document', {'action':'create','title':SUMMARY_TITLE,
                    'body':'已完成班会。暂无记录。'})])
            returns = [part for message in messages[last_user:] for part in message.parts if isinstance(part, ToolReturnPart)]
            if not any(part.tool_name == 'read_class_records' for part in returns):
                return ModelResponse(parts=[ToolCallPart('read_class_records', {})])
            if not any(part.tool_name == 'read_class_work' for part in returns):
                return ModelResponse(parts=[ToolCallPart('read_class_work', {'kind': 'tasks'})])
            if not any(part.tool_name == 'read_summary_delegation' for part in returns):
                return ModelResponse(parts=[ToolCallPart('read_summary_delegation', {})])
            instruction = next(part.content for part in returns if part.tool_name == 'read_summary_delegation')
            if instruction.get('required_material') and not any('班会主题是' in str(part.content)
                    for message in messages for part in message.parts if isinstance(part, UserPromptPart)):
                if plain_question and not any(isinstance(part, RetryPromptPart)
                        for message in messages[last_user:] for part in message.parts):
                    return ModelResponse(parts=[TextPart('班会主题是什么？')])
                return ModelResponse(parts=[ToolCallPart('ask_summary_question', {'question': '班会主题是什么？'})])
            if quiet:
                return ModelResponse(parts=[TextPart('NO_SUMMARY')])
            has_document = any(part.tool_name == 'read_class_work' and 'current_body' in part.content for part in returns)
            if any(part.tool_name == 'prepare_document' and part.content.get('status') == 'existing-document'
                   for part in returns) and not has_document:
                return ModelResponse(parts=[ToolCallPart('read_class_work', {'kind': 'documents', 'search': SUMMARY_TITLE})])
            if before_prepare is not None:
                before_prepare()
            supplemented = any('班会主题是合作' in str(part.content)
                for message in messages for part in message.parts if isinstance(part, (UserPromptPart, ToolReturnPart)))
            task_items = next(part.content['items'] for part in returns if part.tool_name == 'read_class_work'
                and part.content.get('items') and 'task_id' in part.content['items'][0])
            status = {'not-started':'待处理','in-progress':'进行中','waiting':'等待别人','done':'已完成','cancelled':'已取消'}[task_items[0]['status']]
            task_text = task_items[0]['title'] + '：' + status + '。'
            body = ('- 合成学生0交来作品。\n- '+task_text+'\n- '
                    + ('老师补充：班会主题是合作。' if supplemented else '后续继续核对。')
                    if instruction.get('style') == 'three-points' else '## 班级工作小结\n\n合成学生0交来作品。\n\n'+task_text)
            if '班会主题是' in request.text:
                body += '\n\n老师补充：班会主题是合作。'
            return ModelResponse(parts=[ToolCallPart('prepare_document', {'action': 'edit' if has_document else 'create', 'title': SUMMARY_TITLE, 'body': body})])
        return FunctionModel(respond)
    chats = WorkspaceChatBusinessGateway(business.identity, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(query.identity, store, clock=lambda: clock[0])
    sdk = PydanticAgentRuntime(query, model_factory=factory, timeout=30)
    runtime = WorkspaceChatRuntime(chats, history, sdk)
    return chats, history, sdk, runtime, PersonalSummaryService(runtime), calls


async def send(runtime, chats, history, auth, thread, text_value):
    request = uuid4()
    chats.send(auth, thread, request, text_value)
    events = [event async for event in runtime.stream_queued(auth, thread, request)]
    row = history.turn(auth, thread, request)[1]
    assert row['state'] == 'completed', (row, runtime.sdk.last_failure_type)
    assert any(event.type == 'run.completed' for event in events)
    return row


def save(business, auth, row):
    proposal = business.preview(*auth, candidate(row['candidate']))
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    return business.commit(*auth, proposal.proposal_id, uuid4(), approval)


def materials(fixture):
    _, _, _, _, clock, _, commit, c, t, students = fixture
    record = CreateRecord('record.create', uuid4(), c, t, students[0], 'ordinary_fact', clock[0], '合成学生0交来作品', '')
    task = CreateTask('task.create', uuid4(), c, t, '合成作品核对', None, students[0], record.record_id)
    commit(record); commit(task)
    return record, task


@pytest.mark.db
async def test_confirmed_standing_order_discovers_material_without_new_user_request_and_deduplicates(classroom_work):
    business, query, auth, owner, clock, _, _, c, t, _ = classroom_work
    chats, history, sdk, runtime, service, calls = assembly(classroom_work)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理本班的班级工作小结。')
    assert delegated['candidate']['title'] == TITLE
    assert history.summary_programs(auth) == []  # A preview is not a standing order.
    save(business, auth, delegated)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    assert len(history.history(auth, thread)['turns']) == 1  # No material: quiet, no model call.
    initial_calls = len(calls)
    materials(classroom_work)
    await service.check(auth[3])
    rows = history.history(auth, thread)['turns']
    assert len(rows) == 2 and len(calls) > initial_calls, sdk.last_failure_type
    prepared = rows[-1]
    assert prepared['origin'] == 'personal-agent' and prepared['candidate']['title'] == SUMMARY_TITLE
    assert prepared['change_preview']['kind'] == 'create' and prepared['action_receipt'] is None
    assert '合成作品核对：待处理' in prepared['candidate']['body']
    assert len(query.documents(*auth, c, t)) == 1, 'Agent did not save the generated summary'
    saved_calls = len(calls)
    rebuilt = PersonalSummaryService(WorkspaceChatRuntime(chats, history, sdk))
    rebuilt.sessions[auth[3]] = auth
    await rebuilt.check(auth[3]); await service.check(auth[3])
    assert len(calls) == saved_calls and len(history.history(auth, thread)['turns']) == 2
    receipt = save(business, auth, prepared)
    refreshed = history.history(auth, thread)['turns'][-1]
    assert refreshed['action_receipt']['resource_id'] == receipt.resource_id
    document = query.document(*auth, c, t, receipt.resource_id)
    assert document['body'] == prepared['candidate']['body']
    assert not history.recall(auth, thread, '依据已确认', before=3)['items']
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.personal_summary_attempt')).scalar_one() == 1


@pytest.mark.db
async def test_missing_required_material_question_resumes_only_its_chat(classroom_work):
    business, _, auth, _, _, _, _, _, _, _ = classroom_work
    chats, history, sdk, runtime, service, _ = assembly(classroom_work)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理班级小结，需要核对班会主题。')
    save(business, auth, delegated); materials(classroom_work)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    question = history.history(auth, thread)['turns'][-1]
    assert question['origin'] == 'personal-agent' and question['answer_required']
    assert question['candidate'] is None and question['assistant_text'] == '班会主题是什么？', sdk.last_failure_type
    other = await send(runtime, chats, history, auth, uuid4(), '是')
    assert other['candidate'] is None
    answer = await send(runtime, chats, history, auth, thread, '班会主题是合作。')
    assert answer['candidate'] and answer['candidate']['command'] == 'document.create', (answer, sdk.last_failure_type)
    assert '老师补充' in answer['candidate']['body']
    assert history.history(auth, thread)['turns'][-2]['assistant_text'] == question['assistant_text']


@pytest.mark.db
async def test_long_term_feedback_and_one_off_override_do_not_mix_and_pause_stops_work(classroom_work):
    business, _, auth, _, clock, _, _, _, _, _ = classroom_work
    chats, history, sdk, runtime, service, calls = assembly(classroom_work)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理班级工作小结。')
    save(business, auth, delegated)
    once = await send(runtime, chats, history, auth, thread, '这次详细一点。')
    assert once['candidate'] is None
    assert history.summary_programs(auth)[0]['style'] == 'standard'
    feedback = await send(runtime, chats, history, auth, thread, '以后用三条要点整理小结。')
    assert feedback['change_preview']['kind'] == 'edit'
    save(business, auth, feedback)
    assert history.summary_programs(auth)[0]['style'] == 'three-points'
    materials(classroom_work); service.sessions[auth[3]] = auth
    await service.check(auth[3])
    prepared = history.history(auth, thread)['turns'][-1]
    assert prepared['candidate']['body'].count('\n- ') == 2, sdk.last_failure_type
    paused = await send(runtime, chats, history, auth, thread, '暂停整理班级小结。')
    save(business, auth, paused)
    assert history.summary_programs(auth) == []
    clock[0] += timedelta(minutes=2)
    called = len(calls)
    await service.check(auth[3])
    assert len(calls) == called


@pytest.mark.db
async def test_provider_failure_is_persisted_and_not_automatically_redispatched(classroom_work):
    business, _, auth, _, clock, _, _, _, _, _ = classroom_work
    chats, history, _, runtime, service, calls = assembly(classroom_work, fail=True)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理班级工作小结。')
    save(business, auth, delegated); materials(classroom_work)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    failed = history.history(auth, thread)['turns'][-1]
    assert failed['origin'] == 'personal-agent' and failed['state'] == 'failed' and failed['candidate'] is None
    called = len(calls); clock[0] += timedelta(minutes=2)
    await service.check(auth[3])
    assert len(calls) == called
    # Explicit retry carries the failed initiative's confirmed scope before
    # model/tool selection; it does not need to rediscover or enable it.
    chats, history, _, runtime, _, _ = assembly(classroom_work)
    retried = await send(runtime, chats, history, auth, thread, '继续整理班级工作小结。')
    assert retried['origin'] == 'user' and retried['candidate']['title'] == SUMMARY_TITLE


@pytest.mark.db
async def test_quiet_model_result_and_stale_source_rejection_preserve_business(classroom_work):
    from class_os.application.roster import CommandRejected
    business, query, auth, _, clock, _, commit, c, t, _ = classroom_work
    chats, history, _, runtime, service, calls = assembly(classroom_work, quiet=True)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理班级工作小结。')
    save(business, auth, delegated)
    _, task = materials(classroom_work)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    quiet_turn = history.history(auth, thread)['turns'][-1]
    assert quiet_turn['state'] == 'completed' and quiet_turn['candidate'] is None
    assert quiet_turn['assistant_text'] == 'NO_SUMMARY' and not quiet_turn['answer_required']
    assert len(query.documents(*auth, c, t)) == 1
    called = len(calls)
    await service.check(auth[3]); assert len(calls) == called
    # A new source version is a new opportunity, not a repeat of the old one.
    clock[0] += timedelta(minutes=2)
    commit(ChangeTask('task.update', task.task_id, c, t, 1, 'waiting', '等待确认'))
    _, _, _, _, fresh, _ = assembly(classroom_work)
    fresh.sessions[auth[3]] = auth
    await fresh.check(auth[3])
    draft = history.history(auth, thread)['turns'][-1]
    assert draft['candidate'] is not None
    proposal = business.preview(*auth, candidate(draft['candidate']))
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    commit(ChangeTask('task.complete', task.task_id, c, t, 2, 'done', '已经核对'))
    with pytest.raises(CommandRejected):
        business.commit(*auth, proposal.proposal_id, uuid4(), approval)
    with pytest.raises(CommandRejected):
        business.preview(*auth, candidate(draft['candidate']))
    assert len(query.documents(*auth, c, t)) == 1


@pytest.mark.db
async def test_queued_restart_and_concurrent_checks_do_not_repeat_work(classroom_work):
    import asyncio
    business, _, auth, _, clock, _, _, _, _, _ = classroom_work
    chats, history, sdk, runtime, service, calls = assembly(classroom_work)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理班级工作小结。')
    save(business, auth, delegated); materials(classroom_work)
    program = history.summary_programs(auth)[0]
    queued = chats.summary_claim(auth, program['document_id'])
    assert queued['state'] == 'queued' and queued['origin'] == 'personal-agent'
    second = PersonalSummaryService(WorkspaceChatRuntime(chats, history, sdk))
    service.sessions[auth[3]] = second.sessions[auth[3]] = auth
    await asyncio.gather(service.check(auth[3]), second.check(auth[3]))
    assert len(history.history(auth, thread)['turns']) == 2
    assert history.history(auth, thread)['turns'][-1]['candidate'] is not None
    called = len(calls)
    await second.check(auth[3]); assert len(calls) == called


@pytest.mark.db
async def test_source_change_during_inference_never_releases_a_ready_draft(classroom_work):
    business, query, auth, _, _, _, commit, c, t, _ = classroom_work
    updated = []
    holder = {}
    def change():
        if not updated:
            task = holder['task']
            commit(ChangeTask('task.complete', task.task_id, c, t, 1, 'done', '已经核对'))
            updated.append(True)
    chats, history, _, runtime, service, _ = assembly(classroom_work, before_prepare=change)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理班级工作小结。')
    save(business, auth, delegated)
    _, holder['task'] = materials(classroom_work)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    result = history.history(auth, thread)['turns'][-1]
    assert updated and result['state'] == 'completed' and result['candidate'] is None
    assert '已更新' in result['assistant_text']
    assert len(query.documents(*auth, c, t)) == 1


@pytest.mark.db
async def test_expired_running_initiative_settles_unknown_without_model_redispatch(classroom_work):
    business, _, auth, _, clock, _, _, _, _, _ = classroom_work
    chats, history, _, runtime, service, calls = assembly(classroom_work)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理班级工作小结。')
    save(business, auth, delegated); materials(classroom_work)
    queued = chats.summary_claim(auth, history.summary_programs(auth)[0]['document_id'])
    claimed = chats.claim(auth, thread, queued['request_id'])
    clock[0] = claimed['lease_until'] + timedelta(seconds=1)
    service.sessions[auth[3]] = auth
    called = len(calls)
    await service.check(auth[3])
    assert len(calls) == called
    assert history.turn(auth, thread, queued['request_id'])[1]['state'] == 'unknown'


@pytest.mark.db
async def test_failed_initiative_manual_retry_question_survives_service_restart(classroom_work):
    business, _, auth, owner, _, _, _, _, _, _ = classroom_work
    chats, history, _, runtime, service, _ = assembly(classroom_work, fail=True, plain_question=True)
    thread = uuid4()
    delegated = await send(runtime, chats, history, auth, thread, '以后持续整理班级小结，需要核对班会主题。')
    save(business, auth, delegated); materials(classroom_work)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    assert history.history(auth, thread)['turns'][-1]['state'] == 'failed'
    retried = await send(runtime, chats, history, auth, thread, '继续整理班级工作小结。')
    assert retried['origin'] == 'user' and retried['candidate'] is None
    assert retried['assistant_text'] == '班会主题是什么？'
    assert history.listing(auth)['data'][0]['summary_attention']
    with owner.transaction(read_only=True) as connection:
        from class_os.infrastructure.personal_summary_store import validate_summary_integrity
        validate_summary_integrity(connection)
    # Fresh runtime has no in-memory pending question; linkage is in PostgreSQL.
    chats, history, _, runtime, _, _ = assembly(classroom_work, premature_answer=True)
    failed_request = uuid4()
    chats.send(auth, thread, failed_request, '班会主题是合作。')
    chats.finish(auth, chats.claim(auth, thread, failed_request), 'failed')
    assert history.listing(auth)['data'][0]['summary_attention']
    answer = await send(runtime, chats, history, auth, thread, '班会主题是合作。')
    assert answer['candidate'] and '老师补充' in answer['candidate']['body']
    save(business, auth, answer)
    assert not history.listing(auth)['data'][0]['summary_attention']
