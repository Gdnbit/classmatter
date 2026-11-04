"""Internal fixed data projection under real ISB/PG; no user export port yet."""
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.identity import digest
from class_os.application.roster import CommandRejected
from class_os.domain.roster import CreateClass, ChangeClass
from class_os.domain.documents import ReviseDocument, ChangeDocumentState
from class_os.domain.workbench_export import validate_package
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.durable_agent import DurableChatRuntime
from test_workbench_composition import workbench
from test_documents_gateway import documents, control, storage, roster, identity, create, saved


def collect(value):
    worker, query, store, _, _, control = value
    token, client, csrf, workspace = control[6]
    # Trusted fixture exercises the internal format with a real identity lease
    # and serialized transaction. This is not a registered QG/HTTP export or a
    # substitute for the future BCG Risk-X preview/approval/receipt path.
    with worker.identity.authorized_session(token, client, workspace, csrf) as subject:
        binding = dict(workspace_id=subject.workspace_id, actor_id=subject.owner_id,
            session_digest=subject.session_id, client_digest=digest(client), csrf_digest=digest(csrf))
        with store.atomic() as tx:
            now = query.clock(); tx.authorized_at = now
            return tx._workbench_data_bundle(binding, now)


@pytest.mark.db
async def test_projection_keeps_all_classes_all_document_versions_audit_and_actual_sdk_history(workbench):
    worker, query, _, owner, _, control = workbench
    credentials = control[6]
    command = create(workbench); saved(workbench, command)
    for change in (ReviseDocument(command.document_id, command.class_id, command.term_id, 1,
            'synthetic revised document', 'retained\r\n<script>not executed</script>', 'markdown'),
        ChangeDocumentState('document.archive', command.document_id, command.class_id, command.term_id, 2),
        ChangeDocumentState('document.restore', command.document_id, command.class_id, command.term_id, 3)):
        saved(workbench, change)
    thread = uuid4()
    worker.create_conversation(*credentials, command.class_id, command.term_id, thread, uuid4(), 'synthetic retained conversation')
    runtime = DurableChatRuntime(worker, query, PydanticAgentRuntime(query))
    events = [event async for event in runtime.stream(credentials, command.class_id, command.term_id,
        thread, uuid4(), 'synthetic retained input', 'chat')]
    assert any(event.type == 'run.completed' for event in events)
    first = query.context(*credentials)
    archive = ChangeClass('class.archive', first.class_id, first.term_id, first.version, first.name)
    proposal = worker.preview(*credentials, archive)
    worker.commit(*credentials, proposal.proposal_id, uuid4(), worker.approve(*credentials, proposal.proposal_id, proposal.payload_hash))
    # Preserve frozen R1's one-active-class rule. The archive must include
    # historical and current class data, not invent parallel active classes.
    second = CreateClass(uuid4(), uuid4(), 'synthetic other class', 'synthetic other term', date(2026, 9, 1), date(2027, 6, 30))
    proposal = worker.preview(*credentials, second)
    worker.commit(*credentials, proposal.proposal_id, uuid4(), worker.approve(*credentials, proposal.proposal_id, proposal.payload_hash))
    from class_os.domain.documents import CreateDocument
    another = CreateDocument(uuid4(), second.class_id, second.term_id, 'other class draft', 'not a first-page projection', 'plain-text')
    saved(workbench, another)
    query.document(*credentials, command.class_id, command.term_id, command.document_id)
    query.page(*credentials, second.class_id, second.term_id)
    package = collect(workbench)
    counts = validate_package(package)
    assert counts['working_document'] == 2 and counts['working_document_revision'] == 5
    assert {row['class_id'] for row in package['documents']['working_document']} == {str(command.class_id), str(second.class_id)}
    assert len(package['legacy_component']['conversations']['conversation_message']) == 2
    assert len(package['legacy_component']['conversations']['conversation_result_receipt']) == 1
    assert package['documents']['working_document_revision']
    with owner.transaction(read_only=True) as connection:
        assert len(package['legacy_component']['audit_refs']) + len(package['document_audit']) == connection.execute(text('SELECT count(*) FROM class_os.business_audit')).scalar_one()
        assert connection.execute(text('SELECT count(*) FROM class_os.export_job')).scalar_one() == 0
    assert not package['activation_allowed'] and not package['complete_exit']


@pytest.mark.db
@pytest.mark.parametrize('name', ['conversation-transfer.dpapi', 'conversation-retirement.dpapi',
    'conversation-import.dpapi', 'conversation-admission.dpapi'])
def test_internal_projection_still_refuses_file_first_lifecycle_fences(workbench, name):
    saved(workbench, create(workbench))
    evidence = workbench[5][3].root / name
    evidence.write_bytes(b'synthetic fenced source, not an activation proof')
    with pytest.raises(CommandRejected):
        collect(workbench)


@pytest.mark.db
def test_unbound_projection_has_no_implicit_authorization_or_export_job(workbench):
    with workbench[2].atomic() as tx:
        with pytest.raises(CommandRejected):
            tx._workbench_data_bundle({}, workbench[1].clock())
