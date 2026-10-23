from datetime import timedelta
from copy import deepcopy
from uuid import uuid4
import re
import json
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.roster import CommandRejected
from class_os.domain.exit_package import AUDIT_ACTIONS, CreateExitExport, checksum, validate_package
from class_os.domain.activity import CreateTask
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity


@pytest.mark.db
def test_exit_audit_action_registry_matches_actual_migrated_constraint(roster):
    with roster[5].transaction(read_only=True) as connection:
        definition = connection.execute(text("""SELECT pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint
            WHERE conrelid='class_os.business_audit'::regclass AND conname='business_audit_action_check'""")).scalar_one()
    assert frozenset(re.findall(r"'([^']+)'", definition)) == AUDIT_ACTIONS


@pytest.mark.db
def test_w2_core_exit_is_idempotent_consistent_and_expiring(roster, tmp_path):
    gateway, query, _, credentials, _, owner, clock = roster
    classroom, student, record = seed(roster)
    submit(gateway, credentials, record)
    task = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成退出跟进", student_id=student.student_id, source_record_id=record.record_id)
    submit(gateway, credentials, task)
    summary = query.exit_summary(*credentials)
    command = CreateExitExport(uuid4(), summary.core_hash)
    preview = gateway.preview(*credentials, command)
    assert preview.risk == "W2"
    with pytest.raises(CommandRejected):
        gateway.commit(*credentials, preview.proposal_id, uuid4())
    proof = gateway.approve(*credentials, preview.proposal_id, preview.payload_hash)
    key = uuid4()
    receipt = gateway.commit(*credentials, preview.proposal_id, key, proof)
    assert gateway.commit(*credentials, preview.proposal_id, key, proof) == receipt
    artifact = query.exit_download(*credentials, receipt.resource_id)
    counts = validate_package(artifact.bundle)
    assert counts == summary.counts and counts["record_revision"] == 1 and counts["manual_task"] == 1
    assert artifact.bundle["core_checksum"] == summary.core_hash
    assert artifact.bundle["audit_refs"] and all("session_digest" not in row for row in artifact.bundle["audit_refs"])
    # Consume an actual BCG-approved/QG-downloaded package, not mock success.
    original, transferred = tmp_path / "original.json", tmp_path / "transferred.json"
    raw = json.dumps(artifact.bundle, ensure_ascii=False).encode("utf-8")
    original.write_bytes(raw)
    transferred.write_bytes(raw)
    def database_counts():
        with owner.transaction(read_only=True) as connection:
            return tuple(connection.execute(text(f"SELECT count(*) FROM class_os.{table}")).scalar_one()
                         for table in ("record_revision", "manual_task", "command_receipt", "export_job", "business_audit"))
    before_verify = database_counts()
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "verify_exit.py"),
                             str(original), "--compare-with", str(transferred)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and not result.stderr
    verification = json.loads(result.stdout)
    assert verification["comparison"] == {"same_file_bytes": True, "same_package": True, "same_core": True}
    assert verification["lifecycle_complete"] is False and verification["counts"] == summary.counts
    assert database_counts() == before_verify
    assert original.read_bytes() == transferred.read_bytes() == raw
    # Recompute hashes deliberately: semantic rejection must not rely only on
    # a digest mismatch or trust a forged "valid" marker in an imported file.
    for mutation in ("inference", "missing-term", "history-gap"):
        forged = deepcopy(artifact.bundle)
        if mutation == "inference":
            forged["core"]["record_revision"][0]["kind"] = "AIInference"
        elif mutation == "missing-term":
            forged["core"]["academic_term"] = []
        else:
            forged["core"]["record_revision"][0].update(version=2, revision_kind="correct", revision_reason="合成伪造留史")
        forged["core_checksum"] = checksum(forged["core"])
        forged["package_checksum"] = checksum({key: value for key, value in forged.items() if key != "package_checksum"})
        with pytest.raises(ValueError):
            validate_package(forged)
    with pytest.raises(ValueError, match="Lifecycle"):
        validate_package(artifact.bundle, require_complete=True)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.export_job")).scalar_one() == 1
        assert connection.execute(text("SELECT payload_hash FROM class_os.business_audit WHERE action='exit.download'")).scalar_one() == artifact.package_hash
    with pytest.raises(ProgrammingError) as denied:
        with roster[2].database.transaction(read_only=True) as connection:
            connection.execute(text("SELECT session_digest FROM class_os.business_audit"))
    assert denied.value.orig.sqlstate == "42501"
    clock[0] += timedelta(minutes=30)
    # Existing credentials idle-time out first; re-login before checking job TTL.
    from test_identity import PASSWORD, CLIENT
    auth = roster[4].login(PASSWORD, CLIENT)
    fresh = (auth.token, CLIENT, auth.csrf, auth.subject.workspace_id)
    with pytest.raises(CommandRejected):
        query.exit_download(*fresh, receipt.resource_id)


@pytest.mark.db
def test_exit_snapshot_change_requires_a_new_preview(roster):
    gateway, query, _, credentials, _, _, _ = roster
    classroom, _, _ = seed(roster)
    command = CreateExitExport(uuid4(), query.exit_summary(*credentials).core_hash)
    preview = gateway.preview(*credentials, command)
    submit(gateway, credentials, CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成新事实世界"))
    with pytest.raises(CommandRejected):
        gateway.approve(*credentials, preview.proposal_id, preview.payload_hash)


@pytest.mark.db
def test_export_commit_and_download_fail_closed_on_audit_outage(roster, monkeypatch):
    gateway, query, store, credentials, _, owner, _ = roster
    seed(roster)
    command = CreateExitExport(uuid4(), query.exit_summary(*credentials).core_hash)
    preview = gateway.preview(*credentials, command)
    proof = gateway.approve(*credentials, preview.proposal_id, preview.payload_hash)
    original = store.audit
    monkeypatch.setattr(store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("injected audit outage")))
    with pytest.raises(RuntimeError):
        gateway.commit(*credentials, preview.proposal_id, uuid4(), proof)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.export_job")).scalar_one() == 0
    monkeypatch.setattr(store, "audit", original)
    receipt = gateway.commit(*credentials, preview.proposal_id, uuid4(), proof)
    monkeypatch.setattr(store, "audit", lambda *args: (_ for _ in ()).throw(RuntimeError("injected audit outage")))
    with pytest.raises(RuntimeError):
        query.exit_download(*credentials, receipt.resource_id)
