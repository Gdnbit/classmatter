"""Actual PostgreSQL suppressed writes must not produce business success."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.domain.activity import CreateTask, ChangeTask, ReviseRecord
from class_os.domain.exit_package import CreateExitExport
from class_os.domain.roster import ChangeClass, CreateStudent, DeactivateStudent, UpdateIdentifier
from test_activity_gateway import seed, submit
from test_roster_gateway import roster, class_command
from test_identity import identity


TABLES = ("academic_term", "school_class", "student", "enrollment", "student_identifier",
          "record_revision", "manual_task", "export_job", "command_proposal", "approval_receipt",
          "command_receipt", "business_audit")


def snapshot(owner):
    with owner.transaction(read_only=True) as connection:
        return {table: connection.execute(text(f"SELECT row_to_json(t)::text FROM class_os.{table} t ORDER BY row_to_json(t)::text")).scalars().all()
                for table in TABLES}


CASES = (
    ("class-create", "academic_term", "INSERT"),
    ("class-create", "school_class", "INSERT"),
    ("student-create", "student", "INSERT"),
    ("student-create", "enrollment", "INSERT"),
    ("class-update", "school_class", "UPDATE"),
    ("class-archive", "academic_term", "UPDATE"),
    ("deactivate", "student", "UPDATE"),
    ("deactivate", "enrollment", "UPDATE"),
    ("identifier", "student_identifier", "INSERT"),
    ("identifier", "student", "UPDATE"),
    ("record", "record_revision", "INSERT"),
    ("record-revise", "record_revision", "INSERT"),
    ("task", "manual_task", "INSERT"),
    ("task-update", "manual_task", "UPDATE"),
    ("export", "export_job", "INSERT"),
    ("receipt", "command_receipt", "INSERT"),
    ("finish-proposal", "command_proposal", "UPDATE"),
    ("finish-approval", "approval_receipt", "UPDATE"),
    ("preview", "command_proposal", "INSERT"),
    ("approve-insert", "approval_receipt", "INSERT"),
    ("approve-replace", "approval_receipt", "UPDATE"),
    ("approve-state", "command_proposal", "UPDATE"),
    ("reject-state", "command_proposal", "UPDATE"),
    ("reject-approval", "approval_receipt", "UPDATE"),
)


@pytest.mark.db
@pytest.mark.parametrize("operation,table,event", CASES)
def test_suppressed_business_write_rolls_back_entire_transaction(roster, operation, table, event):
    gateway, query, _, credentials, _, owner, clock = roster
    if operation == "class-create":
        command = class_command()
    else:
        classroom, student, record = seed(roster)
        task = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成落库确认")
        command = task
        if operation == "student-create":
            command = CreateStudent(uuid4(), classroom.class_id, classroom.term_id, 1, "合成第二学生")
        elif operation in ("class-update", "class-archive"):
            command = ChangeClass("class.archive" if operation == "class-archive" else "class.update",
                                  classroom.class_id, classroom.term_id, 1, "合成更名")
        elif operation == "deactivate":
            command = DeactivateStudent("student.deactivate", student.student_id, classroom.class_id, classroom.term_id, 1)
        elif operation == "identifier":
            command = UpdateIdentifier("student.update_identifier", uuid4(), student.student_id, classroom.class_id,
                                       classroom.term_id, 1, "合成学校", "school_number", "合成001", clock[0])
        elif operation == "record":
            command = record
        elif operation == "record-revise":
            submit(gateway, credentials, record)
            command = ReviseRecord("record.correct", record.record_id, classroom.class_id, classroom.term_id, 1,
                                   "合成更正", "", "合成确认")
        elif operation == "task-update":
            submit(gateway, credentials, task)
            command = ChangeTask("task.update", task.task_id, classroom.class_id, classroom.term_id, 1, "waiting")
        elif operation in ("export", "finish-approval", "approve-insert", "approve-replace", "approve-state", "reject-approval"):
            command = CreateExitExport(uuid4(), query.exit_summary(*credentials).core_hash)
    proposal = None if operation == "preview" else gateway.preview(*credentials, command)
    proof = None
    if proposal and proposal.risk == "W2" and operation not in ("approve-insert", "approve-state"):
        proof = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    key = uuid4()
    before = snapshot(owner)
    with owner.transaction() as connection:
        connection.execute(text("CREATE FUNCTION class_os.suppress_business_write() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"))
        # Identifiers are a closed test matrix, never request/model input.
        connection.execute(text(f"CREATE TRIGGER suppress_business_write BEFORE {event} ON class_os.{table} FOR EACH ROW EXECUTE FUNCTION class_os.suppress_business_write()"))
    with pytest.raises(RuntimeError, match="Missing durable business mutation"):
        if operation == "preview":
            gateway.preview(*credentials, command)
        elif operation.startswith("approve-"):
            gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
        elif operation.startswith("reject-"):
            gateway.reject(*credentials, proposal.proposal_id)
        else:
            gateway.commit(*credentials, proposal.proposal_id, key, proof)
    assert snapshot(owner) == before
    with owner.transaction() as connection:
        connection.execute(text(f"DROP TRIGGER suppress_business_write ON class_os.{table}"))
        connection.execute(text("DROP FUNCTION class_os.suppress_business_write()"))
    if operation == "preview":
        assert gateway.preview(*credentials, command).proposal_id
    elif operation.startswith("approve-"):
        assert gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    elif operation.startswith("reject-"):
        gateway.reject(*credentials, proposal.proposal_id)
    else:
        receipt = gateway.commit(*credentials, proposal.proposal_id, key, proof)
        assert gateway.commit(*credentials, proposal.proposal_id, key, proof) == receipt
