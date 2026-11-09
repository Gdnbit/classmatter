"""Real PostgreSQL classroom pack; never opens or upgrades the user instance."""
from uuid import uuid4
import pytest
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.application.workbench import WorkbenchBusinessGateway, WorkbenchQueryGateway
from class_os.domain.roster import CreateClass, CreateStudent
from class_os.domain.classroom_work import CreateExam, RecordScore, CreateSeatLayout, AssignSeat, SwapSeats
from class_os.infrastructure.workbench import WorkbenchStore
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.schema_inventory import validate_surface
from class_os.infrastructure.persistence.role_guards import validate_role_guards
from class_os.infrastructure.classroom_work import validate_classroom_integrity
from test_workspace_chat_storage import workspace_chat, roster, identity


@pytest.fixture
def classroom_work(workspace_chat):
    _, _, credentials, old_owner, old_runtime, clock, old_store, boundary = workspace_chat
    owner = Database(old_owner.engine.url, migration=True, profile='classroom-work-d4')
    database = Database(old_runtime.engine.url, profile='classroom-work-d4')
    migrate(owner)
    store = WorkbenchStore(database, old_store.restrictions)
    business = WorkbenchBusinessGateway(boundary, store, clock=lambda: clock[0])
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    def commit(command):
        proposal = business.preview(*credentials, command)
        approval = business.approve(*credentials, proposal.proposal_id, proposal.payload_hash) if proposal.risk == 'W2' else None
        return business.commit(*credentials, proposal.proposal_id, uuid4(), approval)
    from datetime import date
    class_id, term_id = uuid4(), uuid4()
    commit(CreateClass(class_id, term_id, '合成成绩班', '合成学期', date(2026, 9, 1), date(2027, 1, 30)))
    students = [uuid4(), uuid4()]
    for index, student in enumerate(students):
        current = query.context(*credentials)
        commit(CreateStudent(student, class_id, term_id, current.version, f'合成学生{index}'))
    try:
        yield business, query, credentials, owner, clock, store, commit, class_id, term_id, students
    finally:
        owner.close(); database.close()


@pytest.mark.db
def test_exam_results_and_seating_have_real_revisions_and_stale_writes_fail(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    with owner.transaction(read_only=True) as connection:
        validate_surface(connection, complete=True, profile='classroom-work-d4')
        validate_role_guards(connection, profile='classroom-work-d4')
        with pytest.raises(RuntimeError):
            validate_surface(connection, complete=True, profile='workspace-chat-d3')
    exam = uuid4()
    commit(CreateExam(exam, c, t, '合成月考', '数学', '100'))
    first = RecordScore(exam, c, t, students[0], 0, 'scored', '0')
    preview = business.preview(*auth, first)
    assert not query.classroom_read(auth, c, t, exam_id=exam)['results']
    with pytest.raises(CommandRejected):
        business.commit(*auth, preview.proposal_id, uuid4())
    commit(first)
    commit(RecordScore(exam, c, t, students[1], 0, 'absent', None))
    with pytest.raises(CommandRejected):
        business.preview(*auth, RecordScore(exam, c, t, students[0], 1, 'scored', '101', '合成核对'))
    commit(RecordScore(exam, c, t, students[0], 1, 'scored', '85.50', '合成核对'))
    with pytest.raises(CommandRejected):
        business.preview(*auth, first)
    result = query.classroom_read(auth, c, t, exam_id=exam)
    assert result['scored_count'] == 1 and result['average'] == '85.50'
    assert {row['status'] for row in result['results']} == {'scored', 'absent'}
    layout = uuid4()
    commit(CreateSeatLayout(layout, c, t, 2, 3))
    commit(AssignSeat(layout, c, t, 1, students[0], 1, 1))
    commit(AssignSeat(layout, c, t, 2, students[1], 1, 2))
    old_swap = SwapSeats(layout, c, t, 3, 1, 1, 1, 2)
    commit(old_swap)
    with pytest.raises(CommandRejected):
        business.preview(*auth, old_swap)
    with pytest.raises(CommandRejected):
        business.preview(*auth, AssignSeat(layout, c, t, 4, students[0], 1, 1))
    with pytest.raises(CommandRejected):
        business.preview(*auth, AssignSeat(layout, c, t, 4, uuid4(), 2, 1))
    with pytest.raises(CommandRejected):
        query.classroom_read(auth, uuid4(), t, exam_id=exam)
    seating = query.classroom_read(auth, c, t, seating=True)
    assert seating['version'] == 4 and len(seating['seats']) == 6
    assert seating['seats'][0]['student_id'] == students[1] and seating['seats'][1]['student_id'] == students[0]
    # Moving into an empty seat clears the old one in the next complete snapshot.
    commit(AssignSeat(layout, c, t, 4, students[0], 2, 3))
    seating = query.classroom_read(auth, c, t, seating=True)
    assert sum(row['student_id'] == students[0] for row in seating['seats']) == 1
    with owner.transaction(read_only=True) as connection:
        validate_classroom_integrity(connection)
        assert connection.execute(text('SELECT count(*) FROM class_os.exam_result_revision')).scalar_one() == 3
        assert connection.execute(text('SELECT count(*) FROM class_os.seat_revision')).scalar_one() == 30


@pytest.mark.db
def test_score_audit_failure_rolls_back_and_runtime_cannot_rewrite_history(classroom_work, monkeypatch):
    from sqlalchemy.exc import ProgrammingError
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    exam = uuid4()
    commit(CreateExam(exam, c, t, '合成回滚考试', '数学', '100'))
    command = RecordScore(exam, c, t, students[0], 0, 'scored', '90')
    proposal = business.preview(*auth, command)
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    audit = store.audit
    def unavailable(connection, binding, action, outcome, now, metadata):
        if action == 'command.commit' and outcome == 'allowed':
            raise RuntimeError('Synthetic audit unavailable')
        return audit(connection, binding, action, outcome, now, metadata)
    key = uuid4()
    monkeypatch.setattr(store, 'audit', unavailable)
    with pytest.raises(RuntimeError):
        business.commit(*auth, proposal.proposal_id, key, approval)
    monkeypatch.setattr(store, 'audit', audit)
    assert query.classroom_read(auth, c, t, exam_id=exam)['results'] == []
    assert query.command_status(*auth, proposal.proposal_id, key).status == 'not_committed'
    receipt = business.commit(*auth, proposal.proposal_id, key, approval)
    assert business.commit(*auth, proposal.proposal_id, key, approval) == receipt
    with pytest.raises(ProgrammingError):
        with store.database.transaction() as connection:
            connection.execute(text('UPDATE class_os.exam_result_revision SET score=99'))
    with owner.transaction(read_only=True) as connection:
        validate_classroom_integrity(connection)
        assert str(connection.execute(text('SELECT score FROM class_os.exam_result_revision')).scalar_one()) == '90.00'
