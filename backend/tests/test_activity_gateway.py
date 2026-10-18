from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.roster import CommandRejected
from class_os.domain.activity import CreateRecord, ReviseRecord, CreateTask, ChangeTask
from class_os.domain.roster import CreateStudent, ChangeClass, UpdateIdentifier, DeactivateStudent
from test_roster_gateway import roster, create_class
from test_identity import identity


def submit(gateway, credentials, command):
    preview = gateway.preview(*credentials, command)
    proof = gateway.approve(*credentials, preview.proposal_id, preview.payload_hash) if preview.risk == "W2" else None
    return gateway.commit(*credentials, preview.proposal_id, uuid4(), proof)


def seed(roster):
    gateway, query, store, credentials, boundary, owner, clock = roster
    classroom, _ = create_class(gateway, credentials)
    student = CreateStudent(uuid4(), classroom.class_id, classroom.term_id, 1, "合成学生甲")
    submit(gateway, credentials, student)
    clock[0] += timedelta(seconds=1)
    record = CreateRecord("record.create", uuid4(), classroom.class_id, classroom.term_id, student.student_id,
                          "attendance_late_fact", clock[0], "合成学生到校记录", "")
    return classroom, student, record


@pytest.mark.db
def test_record_task_today_timeline_and_revision_share_facts(roster):
    gateway, query, _, credentials, _, owner, clock = roster
    classroom, student, record = seed(roster)
    submit(gateway, credentials, record)
    task = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成跟进", clock[0] - timedelta(seconds=1),
                      student.student_id, record.record_id)
    submit(gateway, credentials, task)
    today = query.projection(*credentials, classroom.class_id, classroom.term_id)
    timeline = query.projection(*credentials, classroom.class_id, classroom.term_id, student_id=student.student_id)
    assert today == timeline
    assert today["tasks"][0]["overdue"] and today["tasks"][0]["status"] == "not-started"
    correction = ReviseRecord("record.correct", record.record_id, classroom.class_id, classroom.term_id, 1, "合成更正事实", "", "教师更正")
    preview = gateway.preview(*credentials, correction)
    assert preview.risk == "W2"
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, preview.proposal_id, uuid4())
    proof = gateway.approve(*credentials, preview.proposal_id, preview.payload_hash)
    gateway.commit(*credentials, preview.proposal_id, uuid4(), proof)
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, correction)
    projection = query.projection(*credentials, classroom.class_id, classroom.term_id)
    assert [r["version"] for r in projection["records"]] == [2, 1]
    assert projection["records"][1]["fact_text"] == record.fact_text
    submit(gateway, credentials, ChangeTask("task.update", task.task_id, task.class_id, task.term_id, 1, "waiting"))
    submit(gateway, credentials, ChangeTask("task.complete", task.task_id, task.class_id, task.term_id, 2, "done", "已完成合成核对"))
    tasks = query.projection(*credentials, classroom.class_id, classroom.term_id)["tasks"]
    assert tasks[0]["version"] == 3 and not tasks[0]["overdue"]
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, ChangeTask("task.update", task.task_id, task.class_id, task.term_id, 3, "in-progress"))
    with owner.transaction() as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 2


@pytest.mark.db
def test_leave_links_are_same_student_ordered_and_do_not_overwrite(roster):
    gateway, query, _, credentials, _, _, _ = roster
    classroom, student, record = seed(roster)
    request = replace(record, kind="leave_requested_fact")
    submit(gateway, credentials, request)
    approval = replace(record, record_id=uuid4(), kind="leave_approved_fact", related_record_id=request.record_id)
    submit(gateway, credentials, approval)
    returned = replace(record, record_id=uuid4(), kind="leave_returned_fact", related_record_id=approval.record_id)
    submit(gateway, credentials, returned)
    bad = replace(returned, record_id=uuid4(), related_record_id=request.record_id)
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, bad)
    assert len(query.projection(*credentials, classroom.class_id, classroom.term_id)["records"]) == 3


@pytest.mark.db
def test_sensitive_record_and_its_task_cannot_downgrade_risk(roster):
    gateway, _, _, credentials, _, _, _ = roster
    classroom, student, record = seed(roster)
    record = replace(record, kind="conversation_fact")
    assert gateway.preview(*credentials, record).risk == "W2"
    submit(gateway, credentials, record)
    task = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成谈话跟进", student_id=student.student_id, source_record_id=record.record_id)
    assert gateway.preview(*credentials, task).risk == "W2"


@pytest.mark.db
def test_identifier_duplicates_are_candidates_without_merge(roster):
    gateway, query, _, credentials, _, _, clock = roster
    classroom, first, _ = seed(roster)
    second = replace(first, student_id=uuid4(), name="合成学生乙")
    submit(gateway, credentials, second)
    identifier = UpdateIdentifier("student.update_identifier", uuid4(), first.student_id, classroom.class_id, classroom.term_id,
                                  1, "synthetic-school", "school_number", "SYN-0001", clock[0])
    submit(gateway, credentials, identifier)
    submit(gateway, credentials, replace(identifier, identifier_id=uuid4(), student_id=second.student_id))
    duplicates = query.projection(*credentials, classroom.class_id, classroom.term_id, view="duplicates")
    assert len(duplicates) == 1 and duplicates[0]["reason"] == "identifier_conflict"
    assert len(query.roster(*credentials, classroom.class_id, classroom.term_id)) == 2
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, replace(identifier, identifier_id=uuid4(), expected_version=2))


@pytest.mark.db
def test_archive_retains_history_and_rejects_new_business_writes(roster):
    gateway, query, _, credentials, _, _, _ = roster
    classroom, student, record = seed(roster)
    submit(gateway, credentials, record)
    submit(gateway, credentials, ChangeClass("class.archive", classroom.class_id, classroom.term_id, 1, classroom.name))
    assert query.context(*credentials) is None
    assert query.history(*credentials)[0]["status"] == "archived"
    assert len(query.projection(*credentials, classroom.class_id, classroom.term_id)["records"]) == 1
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, replace(record, record_id=uuid4()))


@pytest.mark.db
def test_deactivation_rejects_empty_interval_then_preserves_history(roster):
    gateway, query, _, credentials, _, owner, clock = roster
    classroom, _ = create_class(gateway, credentials)
    student = CreateStudent(uuid4(), classroom.class_id, classroom.term_id, 1, "合成即时入班学生")
    submit(gateway, credentials, student)
    deactivate = DeactivateStudent("student.deactivate", student.student_id, classroom.class_id, classroom.term_id, 1)
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, deactivate)
    clock[0] += timedelta(microseconds=1)
    receipt = submit(gateway, credentials, deactivate)
    assert receipt.version == 2
    assert query.roster(*credentials, classroom.class_id, classroom.term_id)[0].status == "inactive"
    with owner.transaction(read_only=True) as connection:
        row = connection.execute(text("SELECT valid_from,valid_to FROM class_os.enrollment")).one()
        assert row.valid_to > row.valid_from


@pytest.mark.db
def test_activity_audit_failure_rolls_back_and_record_table_is_append_only(roster, monkeypatch):
    gateway, query, store, credentials, _, _, _ = roster
    classroom, _, record = seed(roster)
    preview = gateway.preview(*credentials, record)
    original = store.audit
    monkeypatch.setattr(store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("injected audit outage")))
    with pytest.raises(RuntimeError):
        gateway.commit(*credentials, preview.proposal_id, uuid4())
    monkeypatch.setattr(store, "audit", original)
    assert not query.projection(*credentials, classroom.class_id, classroom.term_id)["records"]
    submit(gateway, credentials, record)
    with pytest.raises(ProgrammingError) as failure:
        with store.database.transaction() as connection:
            connection.execute(text("UPDATE class_os.record_revision SET fact_text='overwrite'"))
    assert failure.value.orig.sqlstate == "42501"
