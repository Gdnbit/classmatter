"""Built-in preparation needs evidence, not an activation phrase or mandate."""
import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.domain.personal_summary import SUMMARY_TITLE, TITLE
from class_os.domain.activity import ChangeTask
from class_os.application.roster import CommandRejected
from class_os.domain.workspace_chat import candidate
from class_os.infrastructure.personal_summary_runtime import PersonalSummaryService
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from class_os.infrastructure.personal_summary_store import validate_summary_integrity
from test_personal_summary_runtime import assembly, materials, save, send, classroom_work, workspace_chat, roster, identity


@pytest.mark.db
async def test_existing_material_prepares_summary_without_delegation_or_invented_topic(classroom_work):
    business, query, auth, owner, _, _, _, c, t, _ = classroom_work
    materials(classroom_work)
    chats, history, sdk, runtime, service, calls = assembly(classroom_work)
    reports = []
    sdk.diagnostics = reports.append
    assert not query.documents(*auth, c, t)
    programs = history.summary_programs(auth)
    assert len(programs) == 1 and programs[0].get('kind') == 'builtin'
    assert service._builtin_model_ready(auth)
    service.sessions[auth[3]] = auth
    try:
        await service.check(auth[3])
        programs = history.summary_programs(auth)
        assert len(programs) == 1 and programs[0].get('kind') == 'builtin', 'Base work must not require an activation phrase'
        assert calls, (reports, sdk.last_failure_type)
        program = programs[0]
        listing = history.listing(auth)['data']
        assert len(listing) == 1 and listing[0]['summary_attention']
        row = history.history(auth, program['thread_id'])['turns'][-1]
        assert row['origin'] == 'personal-agent' and not row['answer_required']
        assert row['candidate']['title'] == SUMMARY_TITLE and row['candidate']['command'] == 'document.create'
        assert '合成学生0交来作品' in row['candidate']['body'] and '班会主题' not in row['candidate']['body']
        assert not query.documents(*auth, c, t), 'Preparation must not save business documents'
        called = len(calls)
        save(business, auth, row)
        await service.check(auth[3])
        assert len(calls) == called
        documents = query.documents(*auth, c, t)
        assert len(documents) == 1 and documents[0]['title'] == SUMMARY_TITLE
        assert not history.listing(auth)['data'][0]['summary_attention']
        assert history.history(auth, program['thread_id'])['turns'][-1]['action_receipt'] is not None
        assert not history.recall(auth, program['thread_id'], '系统内置', before=2)['items']
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT count(*) FROM class_os.personal_summary_attempt')).scalar_one() == 0
            assert connection.execute(text('SELECT count(*) FROM class_os.builtin_summary_attempt')).scalar_one() == 1
    finally:
        await service.close()


@pytest.mark.db
async def test_empty_material_and_unconfigured_model_stay_quiet(classroom_work):
    _, _, auth, _, _, _, _, _, _, _ = classroom_work
    _, history, sdk, _, service, calls = assembly(classroom_work)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    assert not calls and not history.listing(auth)['data']
    materials(classroom_work)
    sdk.provider_state = None
    await service.check(auth[3])
    assert not calls and not history.listing(auth)['data'], 'A custom model factory alone must not activate background work'
    sdk.provider_state = lambda _: 'not-configured'
    await service.check(auth[3])
    assert not calls and not history.listing(auth)['data']
    await service.close()


@pytest.mark.db
async def test_quiet_builtin_has_no_empty_chat_but_keeps_execution_history(classroom_work):
    _, query, auth, _, clock, _, commit, c, t, _ = classroom_work
    _, task = materials(classroom_work)
    _, history, _, _, service, _ = assembly(classroom_work, quiet=True)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    program = history.summary_programs(auth)[0]
    assert not history.listing(auth)['data']
    assert history.history(auth, program['thread_id'])['turns'][0]['assistant_text'] == 'NO_SUMMARY'
    clock[0] += timedelta(minutes=2)
    commit(ChangeTask('task.update', task.task_id, c, t, 1, 'waiting', '等待确认'))
    _, _, _, _, fresh, _ = assembly(classroom_work)
    fresh.sessions[auth[3]] = auth
    await fresh.check(auth[3])
    assert history.listing(auth)['data'][0]['summary_attention']
    assert len(history.history(auth, program['thread_id'])['turns']) == 2 and not query.documents(*auth, c, t)
    await service.close(); await fresh.close()


@pytest.mark.db
def test_builtin_daily_budget_and_runtime_cannot_rewrite_attempts(classroom_work):
    from sqlalchemy.exc import ProgrammingError
    _, _, auth, owner, clock, store, commit, c, t, _ = classroom_work
    _, task = materials(classroom_work)
    chats, history, _, _, _, _ = assembly(classroom_work)
    program = history.summary_programs(auth)[0]
    for index in range(6):
        queued = chats.summary_claim(auth, program['program_id'])
        assert queued is not None
        chats.cancel(auth, program['thread_id'], queued['request_id'], queued['version'])
        clock[0] += timedelta(minutes=2)
        commit(ChangeTask('task.update', task.task_id, c, t, index + 1,
            'waiting' if index % 2 == 0 else 'in-progress', '合成进展' + str(index)))
    assert chats.summary_claim(auth, program['program_id']) is None
    with pytest.raises(ProgrammingError):
        with store.database.transaction() as connection:
            connection.execute(text('UPDATE class_os.builtin_summary_attempt SET basis_hash=basis_hash'))
    with owner.transaction(read_only=True) as connection:
        validate_summary_integrity(connection)
        assert connection.execute(text('SELECT count(*) FROM class_os.builtin_summary_attempt')).scalar_one() == 6
    with pytest.raises(ValueError):
        with owner.transaction() as connection:
            connection.execute(text('UPDATE class_os.builtin_summary_attempt SET program_id=:id'), {'id': uuid4()})
            validate_summary_integrity(connection)


@pytest.mark.db
async def test_concurrent_restart_source_change_and_stale_save(classroom_work):
    business, query, auth, owner, clock, _, commit, c, t, _ = classroom_work
    _, task = materials(classroom_work)
    chats, history, sdk, runtime, service, calls = assembly(classroom_work)
    program = history.summary_programs(auth)[0]
    queued = chats.summary_claim(auth, program['program_id'])
    assert queued['origin'] == 'personal-agent' and queued['state'] == 'queued'
    rebuilt = PersonalSummaryService(WorkspaceChatRuntime(chats, history, sdk))
    service.sessions[auth[3]] = rebuilt.sessions[auth[3]] = auth
    try:
        await asyncio.gather(service.check(auth[3]), rebuilt.check(auth[3]))
        row = history.history(auth, program['thread_id'])['turns'][-1]
        assert row['candidate'] and len(history.history(auth, program['thread_id'])['turns']) == 1
        called = len(calls)
        await rebuilt.check(auth[3])
        assert len(calls) == called
        proposal = business.preview(*auth, candidate(row['candidate']))
        approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
        clock[0] += timedelta(minutes=2)
        commit(ChangeTask('task.update', task.task_id, c, t, 1, 'waiting', '等待确认'))
        with pytest.raises(CommandRejected):
            business.commit(*auth, proposal.proposal_id, uuid4(), approval)
        with pytest.raises(CommandRejected):
            business.preview(*auth, candidate(row['candidate']))
        assert not query.documents(*auth, c, t)
        await rebuilt.check(auth[3])
        revised = history.history(auth, program['thread_id'])['turns'][-1]
        assert len(calls) > called and '等待别人' in revised['candidate']['body']
        save(business, auth, revised)
        assert len(query.documents(*auth, c, t)) == 1
        with owner.transaction(read_only=True) as connection:
            validate_summary_integrity(connection)
            assert connection.execute(text('SELECT count(*) FROM class_os.builtin_summary_attempt')).scalar_one() == 2
    finally:
        await service.close(); await rebuilt.close()


@pytest.mark.db
async def test_pause_without_prior_delegation_overrides_builtin_and_never_writes_itself(classroom_work):
    business, query, auth, _, _, _, _, c, t, _ = classroom_work
    chats, history, _, runtime, service, calls = assembly(classroom_work)
    row = await send(runtime, chats, history, auth, uuid4(), '暂停整理班级小结。')
    assert row['candidate']['command'] == 'document.create' and '暂停整理' in row['candidate']['body']
    assert history.summary_programs(auth)[0]['kind'] == 'builtin', 'Unconfirmed preference cannot stop base work'
    save(business, auth, row)
    assert history.summary_programs(auth) == []
    materials(classroom_work)
    called = len(calls)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    assert len(calls) == called and len(query.documents(*auth, c, t)) == 1
    header = history.history(auth, row['thread_id'])['thread']
    chats.control(auth, row['thread_id'], header['version'], 'archive')
    await service.check(auth[3])
    assert history.summary_programs(auth) == [] and len(calls) == called, 'Archiving cannot undo a confirmed pause'
    header = history.history(auth, row['thread_id'])['thread']
    chats.control(auth, row['thread_id'], header['version'], 'clear')
    await service.check(auth[3])
    assert history.summary_programs(auth) == [] and len(calls) == called, 'Clearing chat cannot silently resume preparation'
    await service.close()


@pytest.mark.db
async def test_resume_does_not_require_a_new_activation_phrase_or_duplicate_preferences(classroom_work):
    from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart, TextPart
    from pydantic_ai.models.function import FunctionModel
    business, query, auth, _, _, _, _, c, t, _ = classroom_work
    chats, history, sdk, runtime, service, _ = assembly(classroom_work)
    original = sdk.model_factory
    def restore(messages, info):
        if len(info.function_tools) == 1 and info.function_tools[0].name == 'read_task_progress':
            return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
        if any(isinstance(part, ToolReturnPart) and part.tool_name == 'prepare_summary_delegation'
                for part in messages[-1].parts):
            return ModelResponse(parts=[TextPart('好的。')])
        return ModelResponse(parts=[ToolCallPart('prepare_summary_delegation', {'quote': '恢复整理班级小结。', 'action': 'enable'})])
    sdk.model_factory = lambda request: FunctionModel(restore) if request.text == '恢复整理班级小结。' else original(request)
    thread = uuid4()
    already = await send(runtime, chats, history, auth, thread, '恢复整理班级小结。')
    assert already['candidate'] is None and not query.documents(*auth, c, t)
    paused = await send(runtime, chats, history, auth, thread, '暂停整理班级小结。')
    save(business, auth, paused)
    from class_os.infrastructure.workspace_actions import WorkspaceActionCapture
    for quote, action in [('不要恢复整理班级小结。', 'enable'), ('这次恢复整理班级小结。', 'enable'),
                          ('假设恢复整理班级小结。', 'enable'), ('不要暂停整理班级小结。', 'pause'),
                          ('不想恢复整理班级小结。', 'enable'), ('不再恢复整理班级小结。', 'enable'),
                          ('这次暂停整理班级小结。', 'pause')]:
        capture = WorkspaceActionCapture((quote,), classroom_enabled=True)
        tools = {fn.__name__: fn for fn in capture.tools(query, auth, lambda: None, lambda *a, **k: None)}
        outcome = await tools['prepare_summary_delegation'](quote=quote, action=action)
        assert outcome['status'] == 'not-long-term-delegation' and capture.proposed is None
        shortened = quote.removeprefix('不要')
        if shortened != quote:
            outcome = await tools['prepare_summary_delegation'](quote=shortened, action=action)
            assert outcome['status'] == 'not-long-term-delegation' and capture.proposed is None
        assert history.summary_programs(auth) == [] and query.documents(*auth, c, t)[0]['version'] == 1
    restored = await send(runtime, chats, history, auth, thread, '恢复整理班级小结。')
    assert restored['candidate']['command'] == 'document.revise'
    assert restored['candidate']['document_id'] == paused['candidate']['document_id']
    save(business, auth, restored)
    materials(classroom_work)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    assert history.history(auth, thread)['turns'][-1]['candidate']['title'] == SUMMARY_TITLE
    assert len(query.documents(*auth, c, t)) == 1 and history.summary_programs(auth)[0]['state'] == 'enabled'
    await service.close()


@pytest.mark.db
async def test_expired_builtin_is_unknown_not_redispatched_and_archive_not_reopened(classroom_work):
    _, _, auth, owner, clock, _, _, _, _, _ = classroom_work
    materials(classroom_work)
    chats, history, _, _, service, calls = assembly(classroom_work)
    program = history.summary_programs(auth)[0]
    queued = chats.summary_claim(auth, program['program_id'])
    ticket = chats.claim(auth, program['thread_id'], queued['request_id'])
    clock[0] = ticket['lease_until'] + timedelta(seconds=1)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    assert not calls and history.turn(auth, program['thread_id'], queued['request_id'])[1]['state'] == 'unknown'
    thread = history.history(auth, program['thread_id'])['thread']
    chats.control(auth, program['thread_id'], thread['version'], 'archive')
    clock[0] += timedelta(minutes=2)
    await service.check(auth[3])
    assert not calls and history.history(auth, program['thread_id'])['thread']['status'] == 'archived'
    with owner.transaction(read_only=True) as connection:
        validate_summary_integrity(connection)
    await service.close()


@pytest.mark.db
async def test_source_changed_during_builtin_inference_does_not_release_candidate(classroom_work):
    _, query, auth, _, _, _, commit, c, t, _ = classroom_work
    _, task = materials(classroom_work)
    changed = []
    def change():
        if not changed:
            commit(ChangeTask('task.complete', task.task_id, c, t, 1, 'done', '核对完成'))
            changed.append(True)
    _, history, _, _, service, _ = assembly(classroom_work, before_prepare=change)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    program = history.summary_programs(auth)[0]
    row = history.history(auth, program['thread_id'])['turns'][-1]
    assert changed and row['state'] == 'completed' and row['candidate'] is None
    assert '有更新' in row['assistant_text'] and not query.documents(*auth, c, t)
    await service.close()


@pytest.mark.db
@pytest.mark.parametrize('stale', (False, True))
async def test_failed_builtin_manual_retry_retains_attention_and_source_guard(classroom_work, stale):
    from pydantic_ai.models.function import FunctionModel
    business, query, auth, owner, _, _, commit, c, t, _ = classroom_work
    _, task = materials(classroom_work)
    chats, history, sdk, runtime, service, _ = assembly(classroom_work)
    normal = sdk.model_factory
    def unavailable(messages, info):
        raise TimeoutError('Synthetic provider unavailable')
    sdk.model_factory = lambda _: FunctionModel(unavailable)
    service.sessions[auth[3]] = auth
    await service.check(auth[3])
    program = history.summary_programs(auth)[0]
    assert history.history(auth, program['thread_id'])['turns'][-1]['state'] == 'failed'
    sdk.model_factory = normal
    await service.check(auth[3])
    assert len(history.history(auth, program['thread_id'])['turns']) == 1, 'No automatic provider redispatch'
    retried = await send(runtime, chats, history, auth, program['thread_id'], '继续整理班级工作小结。')
    assert retried['candidate'] and retried['origin'] == 'user'
    assert history.listing(auth)['data'][0]['summary_attention']
    if stale:
        commit(ChangeTask('task.complete', task.task_id, c, t, 1, 'done', '已核对'))
        with pytest.raises(CommandRejected):
            business.preview(*auth, candidate(retried['candidate']))
        assert not query.documents(*auth, c, t)
    else:
        save(business, auth, retried)
        assert len(query.documents(*auth, c, t)) == 1 and not history.listing(auth)['data'][0]['summary_attention']
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.builtin_summary_attempt')).scalar_one() == 1
    await service.close()
