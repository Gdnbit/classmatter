"""Same synthetic identity/data world; no profile switch or duplicate seed data."""
from uuid import uuid4

import pytest
import httpx
from sqlalchemy import text

from class_os.application.workbench import WorkbenchBusinessGateway, WorkbenchQueryGateway
from class_os.application.roster import CommandRejected
from class_os.domain.activity import CreateTask
from class_os.domain.exit_package import CreateExitExport
from class_os.domain.conversation_exit import CreateConversationExit
from class_os.infrastructure.workbench import WorkbenchStore
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_documents_gateway import documents, control, storage, roster, identity, create, saved


@pytest.fixture
def workbench(documents):
    store = WorkbenchStore(documents[4], documents[5][3])
    gateway = WorkbenchBusinessGateway(documents[0].identity, store, clock=documents[0].clock)
    query = WorkbenchQueryGateway(documents[0].identity, store, clock=documents[0].clock)
    return gateway, query, store, documents[3], documents[4], documents[5]


@pytest.mark.db
def test_documents_and_existing_roster_tasks_share_identity_scope_and_receipts(workbench):
    command = create(workbench)
    credentials = workbench[5][6]
    before = workbench[1].context(*credentials)
    students = workbench[1].roster(*credentials, command.class_id, command.term_id)
    assert len(students) == 1 and before.class_id == command.class_id
    saved(workbench, command)
    task = CreateTask('task.create', uuid4(), command.class_id, command.term_id, '合成文档后续检查')
    proposal = workbench[0].preview(*credentials, task)
    assert proposal.risk == 'W1'
    workbench[0].commit(*credentials, proposal.proposal_id, uuid4())
    assert workbench[1].document(*credentials, command.class_id, command.term_id, command.document_id)['body'] == command.body
    assert len(workbench[1].roster(*credentials, command.class_id, command.term_id)) == 1
    projection = workbench[1].projection(*credentials, command.class_id, command.term_id)
    assert projection['tasks'][0]['title'] == '合成文档后续检查'
    with workbench[3].transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.owner_account')).scalar_one() == 1
        assert connection.execute(text('SELECT count(*) FROM class_os.school_class')).scalar_one() == 1
        assert connection.execute(text('SELECT count(*) FROM class_os.working_document')).scalar_one() == 1


@pytest.mark.db
def test_conversation_still_reads_after_document_query_audit(workbench):
    command = create(workbench)
    saved(workbench, command)
    credentials = workbench[5][6]
    workbench[1].document(*credentials, command.class_id, command.term_id, command.document_id)
    thread = uuid4()
    workbench[0].create_conversation(*credentials, command.class_id, command.term_id, thread, uuid4(), '合成文档讨论')
    listing = workbench[1].conversation_listing(*credentials, command.class_id, command.term_id)
    assert listing.items[0]['thread_id'] == thread
    history = workbench[1].conversation_page(*credentials, command.class_id, command.term_id, thread)
    assert history.value.history.title == '合成文档讨论'


@pytest.mark.db
def test_old_partial_exit_is_not_offered_as_complete_d2_exit(workbench):
    credentials = workbench[5][6]
    saved(workbench, create(workbench))
    for command in (CreateExitExport(uuid4(), 'a' * 64), CreateConversationExit(uuid4(), 'a' * 64)):
        with pytest.raises(CommandRejected):
            workbench[0].preview(*credentials, command)
    with pytest.raises(CommandRejected):
        workbench[1].exit_summary(*credentials)
    with pytest.raises(CommandRejected):
        workbench[1].conversation_exit_summary(*credentials)
    with workbench[3].transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.export_job')).scalar_one() == 0


@pytest.mark.db
async def test_existing_and_document_http_adapters_use_one_same_gateway(workbench):
    app = create_app(Settings(), identity=workbench[0].identity, business=workbench[0], query=workbench[1],
                     document_business=workbench[0], document_query=workbench[1])
    assert app.state.document_commands_enabled is True
    command = create(workbench)
    saved(workbench, command)
    credentials = workbench[5][6]
    transport = httpx.ASGITransport(app=app, client=('127.0.0.1', 12345), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:8000') as client:
        for name, value in zip(('session', 'client', 'csrf'), credentials[:3]):
            client.cookies.set('class_os_' + name, value, path='/api')
        root = f'/api/workspaces/{credentials[3]}'
        context = await client.get(root + '/context')
        assert context.status_code == 200, context.text
        assert context.json()['data']['class_id'] == str(command.class_id)
        listing = await client.get(root + f'/classes/{command.class_id}/terms/{command.term_id}/documents')
        assert listing.status_code == 200, listing.text
        assert listing.json()['data'][0]['document_id'] == str(command.document_id)


@pytest.mark.db
@pytest.mark.parametrize('file_name', ['conversation-transfer.dpapi', 'conversation-retirement.dpapi',
                                      'conversation-import.dpapi', 'conversation-admission.dpapi'])
def test_new_domain_cannot_bypass_existing_file_only_fences(workbench, file_name):
    command = create(workbench)
    saved(workbench, command)
    evidence = workbench[5][3].root / file_name
    evidence.write_bytes(b'{}')  # Disposable malformed protected evidence must never grant access.
    with pytest.raises(CommandRejected):
        workbench[1].document(*workbench[5][6], command.class_id, command.term_id, command.document_id)
    with pytest.raises(CommandRejected):
        workbench[1].roster(*workbench[5][6], command.class_id, command.term_id)


@pytest.mark.db
async def test_full_sdk_http_composition_keeps_chat_records_documents_and_audit_together(workbench):
    from class_os.infrastructure.agent import PydanticAgentRuntime
    from class_os.interfaces.http.workbench import create_workbench_app
    from class_os.interfaces.http.durable_conversation import create_durable_app
    from class_os.infrastructure.workbench import WorkbenchTransaction
    from class_os.application.conversation_worker import ConversationWorkerGateway
    from class_os.application.conversation_interaction import ConversationInteractionQuery
    command = create(workbench)
    saved(workbench, command)
    credentials = workbench[5][6]
    workbench[1].document(*credentials, command.class_id, command.term_id, command.document_id)
    sdk = PydanticAgentRuntime(workbench[1])  # Existing offline function model; never sends external data.
    with pytest.raises(ValueError, match='profile composition'):
        create_durable_app(Settings(), worker=workbench[0], query=workbench[1], sdk=sdk)
    legacy_worker = ConversationWorkerGateway(workbench[0].identity, workbench[2])
    legacy_query = ConversationInteractionQuery(workbench[0].identity, workbench[2])
    with pytest.raises(ValueError, match='composition'):
        create_durable_app(Settings(), worker=legacy_worker, query=legacy_query, sdk=PydanticAgentRuntime(legacy_query))
    def app():
        return create_workbench_app(Settings(), worker=workbench[0], query=workbench[1],
                                    sdk=PydanticAgentRuntime(workbench[1]))
    def client():
        transport = httpx.ASGITransport(app=app(), client=('127.0.0.1', 12345), raise_app_exceptions=False)
        result = httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:8000')
        for name, value in zip(('session', 'client', 'csrf'), credentials[:3]):
            result.cookies.set('class_os_' + name, value, path='/api')
        return result
    root = f'/api/workspaces/{credentials[3]}'
    context = f'/classes/{command.class_id}/terms/{command.term_id}'
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': credentials[2]}
    thread, request_id = uuid4(), uuid4()
    path = root + '/conversation-d1' + context + f'/conversations/{thread}'
    async with client() as api:
        capabilities = await api.get(root + '/workbench-d2/capabilities')
        assert capabilities.status_code == 200, capabilities.text
        assert capabilities.json()['profile'] == 'workbench-d2' and capabilities.json()['complete_exit'] is False
        assert (await api.get(root + '/conversation-d1/capabilities')).status_code == 404
        activity = await api.get(root + '/conversation-d1' + context + '/activity')
        assert activity.status_code == 200, activity.text
        audit = await api.get(root + context + '/audit')
        assert audit.status_code == 200, audit.text
        assert audit.json()['schema_version'] == 'classmatter.business-audit.v2'
        assert any(row['action'] == 'document.read' for row in audit.json()['entries'])
        created = await api.post(root + '/conversation-d1' + context + '/conversations',
            json={'thread_id': str(thread), 'request_id': str(uuid4()), 'title': '合成同一工作空间', 'student_id': None}, headers=headers)
        assert created.status_code == 200, created.text
        queued = await api.post(path + '/turns', json={'request_id': str(request_id), 'text': '查询合成班级概况', 'mode': 'read'}, headers=headers)
        assert queued.status_code == 200, queued.text
        events = await api.post(path + f'/turns/{request_id}/events', json={}, headers=headers)
        assert events.status_code == 200 and 'event: run.completed' in events.text, events.text
        assert (await api.get(root + '/conversation-d1/exit/summary')).status_code == 409
    async with client() as rebuilt:
        history = await rebuilt.get(path + '/history')
        assert history.status_code == 200, history.text
        assert len(history.json()['history']['messages']) == 2
        document = await rebuilt.get(root + context + f'/documents/{command.document_id}')
        assert document.status_code == 200 and document.json()['data']['body'] == command.body
    class UnregisteredReader(WorkbenchTransaction):
        pass
    with workbench[2].atomic() as transaction:
        reader = UnregisteredReader(transaction._connection, workbench[2])
        reader.authorized_at = workbench[0].clock()
        with pytest.raises(CommandRejected):
            reader.conversation_history({'workspace_id': credentials[3], 'actor_id': workbench[5][5]['owner']},
                                        command.class_id, command.term_id, thread)
