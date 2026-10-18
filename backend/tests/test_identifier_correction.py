from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.roster import CommandRejected
from class_os.domain.roster import UpdateIdentifier, decode
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity


def identifier_pair(roster):
    gateway, _, _, credentials, _, _, clock = roster
    classroom, student, _ = seed(roster)
    old = UpdateIdentifier("student.update_identifier", uuid4(), student.student_id, classroom.class_id,
                           classroom.term_id, 1, "synthetic-school", "school_number", "SYN-OLD", clock[0])
    submit(gateway, credentials, old)
    clock[0] += timedelta(seconds=1)
    new = replace(old, identifier_id=uuid4(), expected_version=2, value="SYN-NEW", valid_from=clock[0],
                  supersedes_identifier_id=old.identifier_id)
    return old, new


@pytest.mark.db
def test_w2_replacement_closes_interval_without_overwriting_old_value(roster):
    gateway, query, _, credentials, _, owner, _ = roster
    old, new = identifier_pair(roster)
    proposal = gateway.preview(*credentials, new)
    assert proposal.risk == "W2"
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, proposal.proposal_id, uuid4())
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    key = uuid4()
    receipt = gateway.commit(*credentials, proposal.proposal_id, key, approval)
    assert receipt.version == 3
    assert gateway.commit(*credentials, proposal.proposal_id, key, approval) == receipt
    rows = query.projection(*credentials, new.class_id, new.term_id, view="identifiers")
    previous = next(row for row in rows if row["identifier_id"] == old.identifier_id)
    assert previous["value"] == "SYN-OLD" and previous["valid_to"] == new.valid_from
    assert len(rows) == 2
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.student")).scalar_one() == 1
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, new)


@pytest.mark.db
def test_invalid_replacement_target_interval_source_and_overlap_fail_closed(roster):
    gateway, _, _, credentials, _, _, clock = roster
    old, new = identifier_pair(roster)
    for invalid in (
        replace(new, supersedes_identifier_id=uuid4()),
        replace(new, authority="different-synthetic-source"),
        replace(new, identifier_type="exam_number"),
        replace(new, valid_from=old.valid_from),
        replace(new, valid_from=clock[0] + timedelta(seconds=1)),
        replace(new, value=old.value),
        replace(new, expected_version=1),
    ):
        with pytest.raises(CommandRejected):
            gateway.preview(*credentials, invalid)


@pytest.mark.db
def test_replacement_audit_failure_rolls_back_both_intervals(roster, monkeypatch):
    gateway, query, store, credentials, _, _, _ = roster
    old, new = identifier_pair(roster)
    proposal = gateway.preview(*credentials, new)
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    original = store.audit
    def fail(*args):
        raise RuntimeError("Synthetic audit outage")
    monkeypatch.setattr(store, "audit", fail)
    from class_os.application.roster import AuditUnavailable
    with pytest.raises(AuditUnavailable, match="audit unavailable"):
        gateway.commit(*credentials, proposal.proposal_id, uuid4(), approval)
    monkeypatch.setattr(store, "audit", original)
    rows = query.projection(*credentials, new.class_id, new.term_id, view="identifiers")
    assert len(rows) == 1 and rows[0]["identifier_id"] == old.identifier_id and rows[0]["valid_to"] is None
    assert query.roster(*credentials, new.class_id, new.term_id)[0].version == 2


@pytest.mark.db
def test_replacement_permission_does_not_allow_value_overwrite_or_delete(roster):
    _, _, store, _, _, _, _ = roster
    identifier_pair(roster)
    for statement in ("UPDATE class_os.student_identifier SET value='overwrite'", "DELETE FROM class_os.student_identifier"):
        with pytest.raises(ProgrammingError) as failure:
            with store.database.transaction() as connection:
                connection.execute(text(statement))
        assert failure.value.orig.sqlstate == "42501"


@pytest.mark.db
def test_corrected_duplicate_no_longer_current_but_students_stay_independent(roster):
    gateway, query, _, credentials, _, _, clock = roster
    old, new = identifier_pair(roster)
    from class_os.domain.roster import CreateStudent
    other = CreateStudent(uuid4(), old.class_id, old.term_id, 1, "另一位合成学生")
    submit(gateway, credentials, other)
    duplicate = replace(old, identifier_id=uuid4(), student_id=other.student_id)
    submit(gateway, credentials, duplicate)
    assert len(query.projection(*credentials, old.class_id, old.term_id, view="duplicates")) == 1
    wrong_person = replace(new, supersedes_identifier_id=duplicate.identifier_id)
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, wrong_person)
    submit(gateway, credentials, new)
    assert not query.projection(*credentials, old.class_id, old.term_id, view="duplicates")
    assert len(query.roster(*credentials, old.class_id, old.term_id)) == 2
    ended_target = replace(new, identifier_id=uuid4(), value="SYN-THIRD", expected_version=3,
                           valid_from=clock[0] + timedelta(seconds=1))
    clock[0] += timedelta(seconds=1)
    with pytest.raises(CommandRejected):
        gateway.preview(*credentials, ended_target)
