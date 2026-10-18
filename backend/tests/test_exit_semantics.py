"""Integrity hashes cannot make an invalid typed Record graph importable."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from class_os.domain.activity import KINDS, CreateRecord, ReviseRecord, CreateTask
from class_os.domain.exit_package import CreateExitExport, validate_package
from test_exit_package import rich_package, rehash
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity


def leave_chain(*, step=1):
    bundle = rich_package()
    original = bundle["core"]["record_revision"][0]
    anchor = datetime.fromisoformat(original["occurred_at"])
    rows = []
    for index, kind in enumerate(("leave_requested_fact", "leave_approved_fact", "leave_returned_fact")):
        rows.append({**original, "record_id": str(uuid4()), "kind": kind,
                     "occurred_at": (anchor + timedelta(seconds=index * step)).isoformat(),
                     "recorded_at": (anchor + timedelta(seconds=30)).isoformat(),
                     "related_record_id": rows[-1]["record_id"] if rows else None})
    bundle["created_at"] = (anchor + timedelta(seconds=31)).isoformat()
    bundle["core"]["record_revision"] = rows
    return rehash(bundle)


@pytest.mark.parametrize("kind", tuple(kind for kind in KINDS if kind != "teacher_observation"))
def test_rehashed_fact_kind_cannot_contain_only_observation(kind):
    bundle = leave_chain()
    row = bundle["core"]["record_revision"][-1]
    row.update(kind=kind, fact_text="", observation_text="合成观察不能替代事实正文")
    with pytest.raises(ValueError):
        validate_package(rehash(bundle))


@pytest.mark.parametrize("index", (1, 2))
@pytest.mark.parametrize("fault", ("missing", "wrong-kind", "reverse-time"))
def test_rehashed_leave_followup_requires_owning_predecessor_rules(index, fault):
    bundle = leave_chain()
    rows = bundle["core"]["record_revision"]
    if fault == "missing":
        rows[index]["related_record_id"] = None
    elif fault == "wrong-kind":
        rows[index - 1]["kind"] = "ordinary_fact"
    else:
        rows[index - 1]["occurred_at"] = rows[index + 1]["recorded_at"] if index == 1 else rows[index]["recorded_at"]
    with pytest.raises(ValueError):
        validate_package(rehash(bundle))


@pytest.mark.parametrize("self_link", (True, False))
def test_rehashed_related_record_cycle_cannot_bypass_existing_record_requirement(self_link):
    bundle = rich_package()
    row = bundle["core"]["record_revision"][0]
    row["related_record_id"] = row["record_id"]
    if not self_link:
        second = {**row, "record_id": str(uuid4())}
        row["related_record_id"] = second["record_id"]
        bundle["core"]["record_revision"].append(second)
    with pytest.raises(ValueError):
        validate_package(rehash(bundle))


@pytest.mark.parametrize("step", (0, 1))
def test_valid_leave_chain_keeps_equal_occurrence_times_and_all_revisions(step):
    bundle = leave_chain(step=step)
    assert validate_package(bundle)["record_revision"] == 3


def test_observation_only_is_still_valid_for_observation_kind_and_its_revision():
    bundle = rich_package()
    row = bundle["core"]["record_revision"][0]
    row.update(kind="teacher_observation", fact_text="", observation_text="合成教师观察")
    bundle["core"]["record_revision"].append({**row, "version": 2, "revision_kind": "correct",
                                             "revision_reason": "合成更正观察"})
    assert validate_package(rehash(bundle))["record_revision"] == 2


def test_valid_deep_related_record_chain_does_not_require_python_recursion():
    bundle = rich_package()
    original = bundle["core"]["record_revision"][0]
    rows = []
    for _ in range(1100):
        rows.append({**original, "record_id": str(uuid4()),
                     "related_record_id": rows[-1]["record_id"] if rows else None})
    # Reverse serialized order; graph validity is not array-order authority.
    bundle["core"]["record_revision"] = list(reversed(rows))
    assert validate_package(rehash(bundle))["record_revision"] == 1100


@pytest.mark.db
def test_actual_bcg_leave_chain_and_observation_revisions_export_without_rewriting(roster):
    business, query, _, credentials, _, _, clock = roster
    classroom, student, _ = seed(roster)
    leaves = []
    for kind in ("leave_requested_fact", "leave_approved_fact", "leave_returned_fact"):
        clock[0] += timedelta(seconds=1)
        record = CreateRecord("record.create", uuid4(), classroom.class_id, classroom.term_id, student.student_id,
                              kind, clock[0], "合成请假关联事实", "", leaves[-1].record_id if leaves else None)
        submit(business, credentials, record)
        leaves.append(record)
    observation = CreateRecord("record.create", uuid4(), classroom.class_id, classroom.term_id, student.student_id,
                               "teacher_observation", clock[0], "", "合成观察")
    submit(business, credentials, observation)
    submit(business, credentials, ReviseRecord("record.correct", observation.record_id, classroom.class_id,
                                              classroom.term_id, 1, "", "合成更正观察", "合成修订原因"))
    submit(business, credentials, CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id,
                                            "合成返校核对", student_id=student.student_id, source_record_id=leaves[-1].record_id))
    summary = query.exit_summary(*credentials)
    receipt = submit(business, credentials, CreateExitExport(uuid4(), summary.core_hash))
    bundle = query.exit_download(*credentials, receipt.resource_id).bundle
    assert validate_package(bundle) == summary.counts
    assert bundle["core_checksum"] == summary.core_hash and bundle["lifecycle_status"]["complete"] is False
    rows = bundle["core"]["record_revision"]
    assert len(rows) == 5
    by_id = {row["record_id"]: row for row in rows}
    for index, record in enumerate(leaves):
        assert by_id[str(record.record_id)]["related_record_id"] == (str(leaves[index - 1].record_id) if index else None)
    observations = [row for row in rows if row["record_id"] == str(observation.record_id)]
    assert [row["version"] for row in observations] == [1, 2]
    assert all(row["fact_text"] == "" and row["kind"] == "teacher_observation" for row in observations)
    assert bundle["core"]["manual_task"][0]["source_record_id"] == str(leaves[-1].record_id)
