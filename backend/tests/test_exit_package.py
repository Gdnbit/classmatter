from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from class_os.domain.exit_package import CORE_COLUMNS, MISSING_LIFECYCLE, NONPORTABLE, checksum, validate_package


def package():
    workspace = str(uuid4())
    core = {table: [] for table in CORE_COLUMNS}
    core["workspace"] = [{"workspace_id": workspace, "data_mode": "synthetic-only", "created_at": datetime.now(timezone.utc).isoformat()}]
    value = {"schema_version": "class-os.synthetic-core-exit.v1", "purpose": "synthetic-core-recovery", "workspace_id": workspace,
             "created_at": datetime.now(timezone.utc).isoformat(), "actor_refs": [str(uuid4())], "core": core,
             "core_checksum": checksum(core), "nonportable": list(NONPORTABLE),
             "lifecycle_status": {"complete": False, "missing": list(MISSING_LIFECYCLE)}, "audit_refs": []}
    value["package_checksum"] = checksum(value)
    return value


def test_closed_core_package_is_not_a_complete_exit_claim():
    bundle = package()
    assert validate_package(bundle)["workspace"] == 1
    with pytest.raises(ValueError, match="Lifecycle"):
        validate_package(bundle, require_complete=True)


@pytest.mark.parametrize("mutation", ["unknown", "hash", "scope", "fake-ledger", "secret-column", "missing-collection"])
def test_corrupt_or_overclaiming_package_rejected(mutation):
    bundle = deepcopy(package())
    if mutation == "unknown":
        bundle["secret"] = "synthetic-only-canary"
    elif mutation == "hash":
        bundle["core_checksum"] = "0" * 64
    elif mutation == "scope":
        bundle["core"]["workspace"][0]["workspace_id"] = str(uuid4())
    elif mutation == "fake-ledger":
        bundle["lifecycle_status"] = {"complete": True}
    elif mutation == "secret-column":
        bundle["core"]["workspace"][0]["password_hash"] = "not portable"
    else:
        del bundle["core"]["manual_task"]
    with pytest.raises(ValueError):
        validate_package(bundle)


def rich_package():
    bundle = package()
    w, actor, now = bundle["workspace_id"], bundle["actor_refs"][0], bundle["created_at"]
    term, classroom, student = (str(uuid4()) for _ in range(3))
    common = {"workspace_id": w, "version": 1, "created_by": actor, "updated_by": actor,
              "created_at": now, "updated_at": now}
    bundle["core"]["academic_term"] = [{**common, "term_id": term, "name": "合成学期", "start_date": "2026-09-01", "end_date": "2027-01-30", "status": "active"}]
    bundle["core"]["school_class"] = [{**common, "class_id": classroom, "term_id": term, "name": "合成班级", "status": "active"}]
    bundle["core"]["student"] = [{**common, "student_id": student, "name": "合成学生", "status": "active"}]
    bundle["core"]["student_identifier"] = [{"workspace_id": w, "identifier_id": str(uuid4()), "student_id": student,
        "authority": "合成学校", "identifier_type": "school_number", "value": "合成001", "valid_from": now,
        "valid_to": None, "created_by": actor, "created_at": now}]
    bundle["core"]["manual_task"] = [{**common, "task_id": str(uuid4()), "class_id": classroom, "term_id": term,
        "title": "合成跟进", "student_id": student, "source_record_id": None, "due_at": None,
        "status": "not-started", "evidence": ""}]
    bundle["core"]["record_revision"] = [{"workspace_id": w, "record_id": str(uuid4()), "version": 1,
        "class_id": classroom, "term_id": term, "student_id": student, "kind": "ordinary_fact", "occurred_at": now,
        "recorded_at": now, "recorded_by": actor, "fact_text": "合成事实", "observation_text": "",
        "source": "trusted-ui-synthetic", "related_record_id": None, "revision_kind": "create", "revision_reason": ""}]
    bundle["audit_refs"] = [{"workspace_id": w, "event_id": str(uuid4()), "actor_id": actor, "purpose": "manage-class",
        "action": "command.commit", "outcome": "allowed", "occurred_at": now, "proposal_id": None,
        "payload_hash": None, "receipt_id": None, "resource_id": None, "resource_version": None,
        "class_id": None, "term_id": None}]
    return rehash(bundle)


def rehash(bundle):
    bundle["core_checksum"] = checksum(bundle["core"])
    bundle["package_checksum"] = checksum({key: value for key, value in bundle.items() if key != "package_checksum"})
    return bundle


@pytest.mark.parametrize("table,field,value", [
    ("student_identifier", "authority", {}),
    ("student_identifier", "authority", ""),
    ("student_identifier", "value", "a" * 81),
    ("student_identifier", "value", "bad\x00value"),
    ("student_identifier", "identifier_id", None),
    ("student_identifier", "valid_from", None),
    ("manual_task", "evidence", {"unexpected": "JSON"}),
    ("manual_task", "evidence", "bad\x00evidence"),
    ("manual_task", "evidence", "a" * 501),
    ("manual_task", "version", 2147483648),
    ("student", "created_by", None),
    ("student", "updated_at", None),
    ("student", "updated_at", "2026-10-08🐳12:00:00+00:00"),
])
def test_rehashed_core_still_requires_owning_field_types_and_rules(table, field, value):
    bundle = rich_package()
    assert validate_package(bundle)["manual_task"] == 1
    bundle["core"][table][0][field] = value
    with pytest.raises(ValueError):
        validate_package(rehash(bundle))


@pytest.mark.parametrize("field,value", [
    ("event_id", None), ("action", {}), ("purpose", []), ("resource_version", True),
    ("resource_version", 2147483648), ("payload_hash", "invalid"), ("occurred_at", None),
    ("purpose", "arbitrary-purpose"), ("action", "arbitrary-action"),
])
def test_rehashed_audit_reference_is_not_a_generic_json_container(field, value):
    bundle = rich_package()
    bundle["audit_refs"][0][field] = value
    with pytest.raises(ValueError):
        validate_package(rehash(bundle))


def test_rehashed_lifecycle_false_must_be_a_boolean_not_zero():
    bundle = rich_package()
    bundle["lifecycle_status"]["complete"] = 0
    with pytest.raises(ValueError):
        validate_package(rehash(bundle))


@pytest.mark.parametrize("reason", ("a" * 501, "bad\x00reason", " ", {}))
def test_rehashed_record_revision_preserves_owning_reason_rules(reason):
    bundle = rich_package()
    original = bundle["core"]["record_revision"][0]
    bundle["core"]["record_revision"].append({**original, "version": 2, "revision_kind": "correct", "revision_reason": reason})
    with pytest.raises(ValueError):
        validate_package(rehash(bundle))
