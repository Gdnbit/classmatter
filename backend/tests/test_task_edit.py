from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.roster import CommandRejected
from class_os.domain.activity import CreateTask, ChangeTask, decode_activity
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity


@pytest.mark.db
def test_edit_title_deadline_and_explicit_clear_keep_task_identity(roster):
    gateway, query, _, credentials, _, _, clock = roster
    classroom, student, _ = seed(roster)
    created = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "原合成跟进",
                         student_id=student.student_id)
    submit(gateway, credentials, created)
    updated = ChangeTask("task.update", created.task_id, created.class_id, created.term_id, 1, "not-started",
                         title="修改合成跟进", change_due_date=True, due_at=clock[0] - timedelta(minutes=1))
    receipt = submit(gateway, credentials, updated)
    assert receipt.version == 2 and receipt.resource_id == created.task_id
    task = query.projection(*credentials, created.class_id, created.term_id)["tasks"][0]
    assert task["title"] == updated.title and task["overdue"] and task["status"] == "not-started"
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, updated)
    cleared = replace(updated, expected_version=2, title=None, due_at=None)
    submit(gateway, credentials, cleared)
    task = query.projection(*credentials, created.class_id, created.term_id)["tasks"][0]
    assert task["version"] == 3 and task["due_at"] is None and not task["overdue"]
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, replace(cleared, expected_version=3))
    submit(gateway, credentials, ChangeTask("task.complete", created.task_id, created.class_id, created.term_id, 3,
                                          "done", "合成完成结果"))
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, replace(updated, expected_version=4))


@pytest.mark.db
def test_task_edit_audit_failure_rolls_back_and_sensitive_source_remains_w2(roster, monkeypatch):
    gateway, query, store, credentials, _, _, clock = roster
    classroom, student, record = seed(roster)
    record = replace(record, kind="conversation_fact")
    submit(gateway, credentials, record)
    created = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "敏感合成跟进",
                         student_id=student.student_id, source_record_id=record.record_id)
    submit(gateway, credentials, created)
    edit = ChangeTask("task.update", created.task_id, created.class_id, created.term_id, 1, "not-started", title="新的合成标题")
    proposal = gateway.preview(*credentials, edit)
    assert proposal.risk == "W2"
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    original = store.audit
    def fail(*args):
        raise RuntimeError("Synthetic task audit outage")
    monkeypatch.setattr(store, "audit", fail)
    from class_os.application.roster import AuditUnavailable
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        gateway.commit(*credentials, proposal.proposal_id, uuid4(), approval)
    monkeypatch.setattr(store, "audit", original)
    task = query.projection(*credentials, created.class_id, created.term_id)["tasks"][0]
    assert task["title"] == created.title and task["version"] == 1


def test_task_edit_preserves_legacy_payload_and_rejects_implicit_deadline_or_terminal_edit():
    old = ChangeTask("task.update", uuid4(), uuid4(), uuid4(), 1, "waiting")
    assert "title" not in old.canonical() and "change_due_date" not in old.canonical()
    assert decode_activity(old.canonical()) == old
    new = replace(old, title="合成新标题", due_at=None, change_due_date=True)
    assert decode_activity(new.canonical()) == new
    with pytest.raises(ValueError):
        replace(old, due_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        replace(new, command="task.complete", status="done", evidence="完成")
    with pytest.raises(ValueError):
        replace(new, change_due_date=1)


@pytest.mark.db
def test_edit_permission_does_not_allow_reassigning_task_or_delete(roster):
    _, _, store, _, _, _, _ = roster
    for statement in ("UPDATE class_os.manual_task SET student_id=NULL", "UPDATE class_os.manual_task SET source_record_id=NULL",
                      "DELETE FROM class_os.manual_task"):
        with pytest.raises(ProgrammingError) as failure:
            with store.database.transaction() as connection:
                connection.execute(text(statement))
        assert failure.value.orig.sqlstate == "42501"
