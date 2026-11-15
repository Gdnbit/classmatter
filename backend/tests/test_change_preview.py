"""Frozen factual comparisons, original BCG confirmations and PG reconstruction."""
from datetime import date
from uuid import uuid4
import copy
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from class_os.domain.change_preview import ChangePreview, SeatBoard
from class_os.domain.workspace_chat import candidate, validate_turn, CANDIDATES
from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
from class_os.application.workbench import WorkbenchBusinessGateway, WorkbenchQueryGateway
from class_os.application.roster import CommandRejected
from class_os.infrastructure.workbench import WorkbenchStore
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.workspace_chat import validate_workspace_chat_integrity
from test_workspace_chat_storage import workspace_chat, roster, identity


@pytest.mark.db
def test_all_registered_comparisons_are_factual_frozen_cleared_and_receipt_bound(workspace_chat):
    _, _, auth, old_owner, old_runtime, clock, old_store, boundary = workspace_chat
    owner = Database(old_owner.engine.url, migration=True, profile='classroom-work-d4')
    database = Database(old_runtime.engine.url, profile='classroom-work-d4')
    migrate(owner)
    store = WorkbenchStore(database, old_store.restrictions)
    commands = WorkbenchBusinessGateway(boundary, store, clock=lambda: clock[0])
    business = WorkspaceChatBusinessGateway(boundary, store, clock=lambda: clock[0])
    history = WorkspaceChatQueryGateway(boundary, store, clock=lambda: clock[0])
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    c, t, student, second, task, doc, exam, layout, thread, record, cancelled_task = [uuid4() for _ in range(11)]
    scope = {'class_id': str(c), 'term_id': str(t)}
    saved = []

    def stage(operation, **kwargs):
        payload = {'command': operation, **scope, **kwargs}
        command = candidate(payload)
        request = uuid4()
        business.send(auth, thread, request, '合成前后对比验收')
        ticket = business.claim(auth, thread, request)
        row = business.finish(auth, ticket, 'completed', '请核对这次调整。', command.canonical())
        assert row['change_preview']['candidate_hash'] == row['candidate_hash']
        assert history.turn(auth, thread, request)[1]['action_receipt'] is None
        preview = commands.preview(*auth, command)
        approval = commands.approve(*auth, preview.proposal_id, preview.payload_hash) if preview.risk == 'W2' else None
        receipt = commands.commit(*auth, preview.proposal_id, uuid4(), approval)
        after = history.turn(auth, thread, request)[1]
        assert after['action_receipt']['receipt_id'] == receipt.receipt_id
        assert after['change_preview'] == row['change_preview']
        saved.append((thread, request, copy.deepcopy(after['change_preview'])))
        return after['change_preview']

    try:
        created = stage('class.create', name='合成对比班', term_name='合成学期', start_date='2026-09-01', end_date='2027-01-30')
        assert created['kind'] == 'create' and all(field['before'] is None for field in created['fields'])
        edit = stage('class.update', expected_version=1, name='合成修订班')
        assert edit['fields'][0] == {'field': 'name', 'before': '合成对比班', 'after': '合成修订班'}
        stage('term.update', expected_version=1, previous_name='合成学期', name='合成新学期',
              previous_start_date='2026-09-01', start_date='2026-09-02', previous_end_date='2027-01-30', end_date='2027-01-31')
        stage('student.create', student_id=str(student), expected_class_version=query.context(*auth).version, name='合成学生甲')
        stage('student.create', student_id=str(second), expected_class_version=query.context(*auth).version, name='合成学生乙')
        stage('student.update_name', student_id=str(student), expected_version=1, previous_name='合成学生甲', name='合成学生一')
        created = stage('record.create', record_id=str(record), student_id=str(student), kind='ordinary_fact',
              occurred_at=clock[0].isoformat(), fact_text='合成学生一交来首份回执', observation_text='', related_record_id=None)
        assert created['kind'] == 'create' and all(field['before'] is None for field in created['fields'])
        assert next(field for field in created['fields'] if field['field'] == 'student')['after'] == '合成学生一'
        assert next(field for field in created['fields'] if field['field'] == 'fact_text')['after'] == '合成学生一交来首份回执'
        created = stage('task.create', task_id=str(task), title='合成收集回执', due_at=None, student_id=str(student), source_record_id=str(record))
        assert next(field for field in created['fields'] if field['field'] == 'source')['after'] == '合成学生一交来首份回执'
        edit = stage('task.update', task_id=str(task), expected_version=1, status='waiting', evidence='合成等待', title='合成核对回执')
        assert next(field for field in edit['fields'] if field['field'] == 'title')['before'] == '合成收集回执'
        edit = stage('task.complete', task_id=str(task), expected_version=2, status='done', evidence='合成已核对齐全')
        assert edit['kind'] == 'edit'
        assert next(field for field in edit['fields'] if field['field'] == 'status') == {'field': 'status', 'before': 'waiting', 'after': 'done'}
        assert next(field for field in edit['fields'] if field['field'] == 'evidence') == {'field': 'evidence', 'before': '合成等待', 'after': '合成已核对齐全'}
        stage('task.create', task_id=str(cancelled_task), title='合成备用核对', due_at=None, student_id=None, source_record_id=None)
        edit = stage('task.cancel', task_id=str(cancelled_task), expected_version=1, status='cancelled', evidence='合成不再需要')
        assert next(field for field in edit['fields'] if field['field'] == 'status') == {'field': 'status', 'before': 'not-started', 'after': 'cancelled'}
        assert next(field for field in edit['fields'] if field['field'] == 'evidence')['after'] == '合成不再需要'
        stage('document.create', document_id=str(doc), title='合成小结', body='第一段\n保留段', format='plain-text')
        edit = stage('document.revise', document_id=str(doc), expected_version=1, title='合成修订小结', body='新第一段\n保留段\n新段落', format='plain-text')
        assert next(field for field in edit['fields'] if field['field'] == 'body') == {
            'field': 'body', 'before': '第一段\n保留段', 'after': '新第一段\n保留段\n新段落'}
        stage('exam.create', exam_id=str(exam), title='合成对比月考', subject='数学', maximum_score='100')
        stage('score.record', exam_id=str(exam), student_id=str(student), expected_version=0, status='scored', score='0', reason='')
        edit = stage('score.record', exam_id=str(exam), student_id=str(student), expected_version=1, status='absent', score=None, reason='合成核对')
        assert next(field for field in edit['fields'] if field['field'] == 'score') == {'field': 'score', 'before': '0.00', 'after': None}
        stage('seat.layout.create', layout_id=str(layout), rows=2, columns=3)
        stage('seat.assign', layout_id=str(layout), expected_version=1, student_id=str(student), row=1, column=1)
        stage('seat.assign', layout_id=str(layout), expected_version=2, student_id=str(second), row=1, column=2)
        edit = stage('seat.swap', layout_id=str(layout), expected_version=3, first_row=1, first_column=1, second_row=1, second_column=2)
        assert [cell['student'] for cell in edit['before_seats']['cells'][:2]] == ['合成学生一', '合成学生乙']
        assert [cell['student'] for cell in edit['after_seats']['cells'][:2]] == ['合成学生乙', '合成学生一']
        # The original exact inventory now also exercises every bilateral
        # candidate, not just an exclusion for the newly registered commands.
        from class_os.application.collaboration import CollaborationBusinessGateway
        from class_os.domain.collaboration import Invitation, MaterialMessage, source_citation
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        collaboration = CollaborationBusinessGateway(boundary, store, clock=lambda: clock[0])
        peer = Invitation(workspace_id=uuid4(), name='合成任课同事', endpoint='http://127.0.0.1:18442',
            public_key=Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex())
        collaboration.add_peer(auth, peer, c, t)
        root, material_id, summary_id = uuid4(), uuid4(), uuid4()
        created = stage('collaboration.request', request_id=str(root), peer_id=str(peer.workspace_id),
            thread_id=str(thread), title='合成收集教学进度', body='请提供合成教学进度。')
        assert created['kind'] == 'create'
        assert next(field for field in created['fields'] if field['field'] == 'recipient')['after'] == peer.name
        material = MaterialMessage(message_id=material_id, request_id=root, sender=peer.workspace_id,
            receiver=auth[3], operation='material', title='合成同事文档', body='合成已核对的教学材料。',
            source_document_id=uuid4(), source_version=1)
        collaboration.receive(auth, material)
        notice = business.finish(auth, business.claim(auth, thread, material_id), 'completed', '合成材料已收到。')
        assert notice['candidate'] is None and notice['origin'] == 'collaboration'
        created = stage('collaboration.summary.save', request_id=str(root), source_message_id=str(material_id),
            document_id=str(summary_id), expected_version=0, title='班级工作小结',
            body='合成班级小结。\n\n'+source_citation(peer.name, material), format='markdown')
        assert next(field for field in created['fields'] if field['field'] == 'body')['after'].endswith(material.body)
        incoming = uuid4()
        collaboration.receive(auth, MaterialMessage(message_id=incoming, request_id=incoming,
            sender=peer.workspace_id, receiver=auth[3], operation='request', title='合成核对小结', body='请提供合成修订小结。'))
        request_row = next(row for row in query.collaboration(auth)['items'] if row['message_id'] == incoming)
        thread = request_row['thread_id']
        created = stage('collaboration.material.share', message_id=str(uuid4()), request_id=str(incoming),
            peer_id=str(peer.workspace_id), thread_id=str(thread), document_id=str(doc), expected_version=2,
            title='合成修订小结', body='新第一段\n保留段\n新段落')
        assert next(field for field in created['fields'] if field['field'] == 'body')['after'] == query.document(*auth, c, t, doc)['body']
        assert next(field for field in created['fields'] if field['field'] == 'format')['after'] == 'plain-text'
        stage('document.revise', document_id=str(doc), expected_version=2, title='合成修订小结',
            body='合成发送后的独立修订，不得重写已分享的历史。', format='plain-text')
        # A new store and later edits must not rewrite a past card.
        rebuilt = WorkspaceChatQueryGateway(boundary, WorkbenchStore(database, old_store.restrictions), clock=lambda: clock[0])
        for saved_thread, request, frozen in saved:
            assert rebuilt.turn(auth, saved_thread, request)[1]['change_preview'] == frozen
        with owner.transaction(read_only=True) as connection:
            validate_workspace_chat_integrity(connection)
            from class_os.infrastructure.collaboration_store import validate_collaboration_integrity
            validate_collaboration_integrity(connection)
            kinds = set(connection.execute(text("SELECT candidate->>'command' FROM class_os.workspace_chat_turn WHERE candidate IS NOT NULL")).scalars())
            assert kinds == CANDIDATES
        for saved_thread in {item[0] for item in saved}:
            header = history.history(auth, saved_thread)['thread']
            business.control(auth, saved_thread, header['version'], 'clear')
            assert all(row['change_preview'] is None for row in history.history(auth, saved_thread)['turns'])
        with owner.transaction(read_only=True) as connection:
            validate_workspace_chat_integrity(connection)
    finally:
        owner.close(); database.close()


@pytest.mark.db
def test_changed_context_rejects_original_comparison_without_overwriting_it(workspace_chat):
    # Use the same isolated empty world; a later class rename invalidates the old CAS.
    _, _, auth, old_owner, old_runtime, clock, old_store, boundary = workspace_chat
    owner = Database(old_owner.engine.url, migration=True, profile='classroom-work-d4')
    database = Database(old_runtime.engine.url, profile='classroom-work-d4')
    migrate(owner)
    store = WorkbenchStore(database, old_store.restrictions)
    commands = WorkbenchBusinessGateway(boundary, store, clock=lambda: clock[0])
    chats = WorkspaceChatBusinessGateway(boundary, store, clock=lambda: clock[0])
    reads = WorkspaceChatQueryGateway(boundary, store, clock=lambda: clock[0])
    c, t, thread, request = [uuid4() for _ in range(4)]
    from class_os.domain.roster import CreateClass, ChangeClass
    def commit(value):
        preview = commands.preview(*auth, value)
        approval = commands.approve(*auth, preview.proposal_id, preview.payload_hash)
        return commands.commit(*auth, preview.proposal_id, uuid4(), approval)
    try:
        commit(CreateClass(c, t, '合成原班', '合成学期', date(2026, 9, 1), date(2027, 1, 30)))
        proposed = ChangeClass('class.update', c, t, 1, '合成目标班')
        chats.send(auth, thread, request, '合成改班名')
        row = chats.finish(auth, chats.claim(auth, thread, request), 'completed', '请核对。', proposed.canonical())
        preview = commands.preview(*auth, proposed)
        nonce = commands.approve(*auth, preview.proposal_id, preview.payload_hash)
        commit(ChangeClass('class.update', c, t, 1, '合成并发班'))
        with pytest.raises(CommandRejected):
            commands.commit(*auth, preview.proposal_id, uuid4(), nonce)
        current = reads.turn(auth, thread, request)[1]
        assert current['change_preview'] == row['change_preview'] and current['action_receipt'] is None
        stale_request = uuid4()
        chats.send(auth, thread, stale_request, '合成并发后的旧候选')
        refused = chats.finish(auth, chats.claim(auth, thread, stale_request), 'completed', '已准备好。', proposed.canonical())
        assert refused['candidate'] is None and refused['change_preview'] is None
        assert refused['assistant_text'] == '内容已变化，请重新生成这次操作。'
    finally:
        owner.close(); database.close()


def test_closed_comparison_contract_rejects_incomplete_boards_and_executable_fields():
    for value in [[], [{'row': 1, 'column': 1, 'student': None}] * 2]:
        with pytest.raises(ValidationError):
            SeatBoard(rows=1, columns=2, cells=value)
    with pytest.raises(ValidationError):
        ChangePreview(candidate_hash='a' * 64, kind='edit', fields=[{'field': 'sql', 'before': None, 'after': 'x'}], before_seats=None, after_seats=None)
    cells = [{'row': 1, 'column': column, 'student': '合成同名', 'student_id': str(uuid4())} for column in (1, 2)]
    assert SeatBoard(rows=1, columns=2, cells=cells).cells[0].student_id != cells[1]['student_id']
    cells[1]['student_id'] = cells[0]['student_id']
    with pytest.raises(ValidationError):
        SeatBoard(rows=1, columns=2, cells=cells)
