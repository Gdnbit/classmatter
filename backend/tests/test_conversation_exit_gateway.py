"""Disposable real PG export, protected-source checks, no imports or paid calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from alembic import command as alembic_command
from alembic.config import Config
from class_os.infrastructure.persistence.database import Database, migrate

import pytest
import rfc8785
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.identity import IdentityDenied
from class_os.application.roster import BusinessGateway, CommandRejected
from class_os.application.conversation_exit import ConversationExitBusinessGateway, ConversationExitQueryGateway
from class_os.domain.conversation_control import InitializeConversationControl
from class_os.domain.conversation_exit import CreateConversationExit
from class_os.domain.conversation_exit_v6 import validate_v6
from class_os.domain.exit_package import validate_package
from class_os.infrastructure import conversation_exit as adapter
from class_os.infrastructure.conversation_exit import ConversationExitStore
from class_os.infrastructure.conversation_restrictions import FILE_NAME, ProtectedConversationRestrictions
from test_conversation_control import control, storage, roster, identity, approve, commit, clear
from test_durable_conversation_storage import thread, turn, queued, message


def prepare(control, *, actual=False):
    data = list(control)
    if actual:
        data[3] = ProtectedConversationRestrictions(data[3].root, data[5]["workspace"])
    data[2] = ConversationExitStore(control[2].database, data[3])
    data[0] = ConversationExitBusinessGateway(control[0].identity, data[2], clock=control[0].clock)
    data[1] = ConversationExitQueryGateway(control[1].identity, data[2], clock=control[1].clock)
    commit(data, InitializeConversationControl(uuid4()))
    with data[4].transaction() as connection:
        thread(connection, data[5])
        turn(connection, data[5])
        queued(connection, data[5])
        message(connection, data[5], body="合成耐久导出原文")
    return data


@pytest.fixture
def world(control):
    return prepare(control)


def command(data):
    summary = data[1].conversation_exit_summary(*data[6])
    assert len(summary.counts) == 21
    return CreateConversationExit(uuid4(), summary.snapshot_hash)


def exported(data):
    value = command(data)
    commit(data, value)
    return data[1].conversation_exit_download(*data[6], value.export_id)


@pytest.mark.db
def test_real_bcg_qg_export_covers_conversation_and_not_identity_or_dispatch(world):
    value = command(world)
    proposal, nonce = approve(world, value)
    assert proposal.risk == "X"
    key = uuid4()
    with pytest.raises(CommandRejected):
        world[0].commit(*world[6], proposal.proposal_id, key)
    result = world[0].commit(*world[6], proposal.proposal_id, key, nonce)
    assert world[0].commit(*world[6], proposal.proposal_id, key, nonce) == result
    artifact = world[1].conversation_exit_download(*world[6], value.export_id)
    assert len(validate_v6(artifact.bundle)) == 21 and artifact.package_hash == artifact.bundle["package_checksum"]
    text_bundle = json.dumps(artifact.bundle)
    for forbidden in ("session_digest", "nonce_digest", "password_hash", "sdk_session", "root_binding", "sealed"):
        assert forbidden not in text_bundle
    assert artifact.bundle["activation_allowed"] is False
    assert artifact.bundle["conversations"]["conversation_run"][0]["state"] == "queued"
    assert artifact.bundle["run_authority"] == "source-evidence-only"
    with pytest.raises(ValueError):
        validate_package(artifact.bundle)
    with pytest.raises(ValueError):
        world[1].exit_summary(*world[6])
    with pytest.raises(CommandRejected):
        BusinessGateway(world[0].identity, world[2], clock=world[0].clock).preview(*world[6], command(world))
    with world[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.export_job")).scalar_one() == 1
        assert connection.execute(text("SELECT state,version,generation FROM class_os.conversation_run")).one() == ("queued", 1, None)


@pytest.mark.db
def test_clear_revokes_old_artifact_download_new_export_contains_only_restrictions(world):
    old = exported(world)
    commit(world, clear(world))
    with pytest.raises(CommandRejected):
        world[1].conversation_exit_download(*world[6], old.export_id)
    new = exported(world)
    assert new.bundle["restriction_evidence"]["epoch"] == 1
    assert new.bundle["conversations"]["conversation_message"][0]["body"] is None
    assert "合成耐久导出原文" not in json.dumps(new.bundle, ensure_ascii=False)
    assert validate_v6(new.bundle)


@pytest.mark.db
def test_export_audit_failure_rolls_back_artifact_receipt_then_retries_once(world, monkeypatch):
    value = command(world)
    proposal, nonce = approve(world, value)
    key = uuid4()
    with monkeypatch.context() as patch:
        patch.setattr(world[2], "audit", lambda *args: None)
        with pytest.raises(AuditUnavailable):
            world[0].commit(*world[6], proposal.proposal_id, key, nonce)
    with world[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.export_job")).scalar_one() == 0
    world[0].commit(*world[6], proposal.proposal_id, key, nonce)
    assert world[1].conversation_exit_download(*world[6], value.export_id)


@pytest.mark.db
def test_stale_snapshot_missing_or_ahead_file_and_recent_auth_rejected(world, monkeypatch):
    value = command(world)
    commit(world, clear(world))
    with pytest.raises(CommandRejected):
        world[0].preview(*world[6], value)
    path = world[3].root / FILE_NAME
    saved = path.read_bytes()
    path.unlink()
    with pytest.raises(CommandRejected):
        world[1].conversation_exit_summary(*world[6])
    path.write_bytes(saved)
    world[7][0] += timedelta(minutes=5, seconds=1)
    with pytest.raises(CommandRejected):
        world[0].preview(*world[6], command(world))


@pytest.mark.db
def test_bounded_projection_and_wrong_scope_never_create_partial_export(world, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(adapter, "MAX_BYTES", 1)
        with pytest.raises(CommandRejected):
            world[1].conversation_exit_summary(*world[6])
    with pytest.raises(IdentityDenied):
        world[1].conversation_exit_summary(*world[6][:3], uuid4())
    with pytest.raises(CommandRejected):
        world[1].conversation_exit_download(*world[6], uuid4())
    with world[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.export_job")).scalar_one() == 0


@pytest.mark.db
def test_same_key_concurrent_export_and_expired_download(world):
    value = command(world)
    proposal, nonce = approve(world, value)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as executor:
        result = list(executor.map(lambda _: world[0].commit(*world[6], proposal.proposal_id, key, nonce), range(2)))
    assert result[0] == result[1]
    for _ in range(3):
        world[7][0] += timedelta(minutes=10)
        world[1].term_metadata(*world[6], world[5]["class"], world[5]["term"])
    with pytest.raises(CommandRejected):
        world[1].conversation_exit_download(*world[6], value.export_id)


@pytest.mark.db
def test_pending_clear_refuses_summary_and_old_download(world, monkeypatch):
    old = exported(world)
    proposal, nonce = approve(world, clear(world))
    with monkeypatch.context() as patch:
        patch.setattr(world[2], "audit", lambda *args: None)
        with pytest.raises(AuditUnavailable):
            world[0].commit(*world[6], proposal.proposal_id, uuid4(), nonce)
    with pytest.raises(CommandRejected):
        world[1].conversation_exit_summary(*world[6])
    with pytest.raises(CommandRejected):
        world[1].conversation_exit_download(*world[6], old.export_id)


@pytest.mark.db
def test_assistant_output_keeps_unverified_origin_without_new_fact(world):
    values = world[5]
    with world[4].transaction() as connection:
        connection.execute(text("""UPDATE class_os.conversation_run SET state='completed',version=3,generation=:g,
            started_at=:at,lease_until=:at+interval '1 minute',ended_at=:at"""), {**values, "g": uuid4()})
        message(connection, values, role="assistant", origin="assistant-unverified", body="合成未核实AI解释")
    artifact = exported(world)
    assistant = [row for row in artifact.bundle["conversations"]["conversation_message"] if row["role"] == "assistant"]
    assert assistant[0]["origin"] == "assistant-unverified"
    assert artifact.bundle["core"]["record_revision"] == []


@pytest.mark.db
def test_offline_v2_profile_is_explicit_and_has_no_activation(tmp_path, world):
    artifact = exported(world)
    path, copy = tmp_path / "exit.json", tmp_path / "copy.json"
    path.write_bytes(rfc8785.dumps(artifact.bundle))
    copy.write_bytes(path.read_bytes())
    verifier = Path(__file__).resolve().parents[1] / "verify_exit.py"
    def run(*args):
        return subprocess.run([sys.executable, str(verifier), str(path), *args], capture_output=True, text=True, timeout=10)
    verified = run("--profile", "conversation-v6", "--compare-with", str(copy))
    assert verified.returncode == 0
    output = json.loads(verified.stdout)
    assert output["activation_allowed"] is False and output["comparison"]["same_source_snapshot"]
    assert run().returncode == 1
    assert run("--profile", "conversation-v2").returncode == 1
    assert run("--profile", "conversation-v3").returncode == 1
    assert run("--profile", "conversation-v4").returncode == 1
    assert run("--profile", "conversation-v6", "--require-complete").returncode == 1
    assert run("--profile", "conversation-v6", "--activate").returncode == 2
    copy.write_text(json.dumps(artifact.bundle, indent=2), encoding="utf-8")
    assert run("--profile", "conversation-v6", "--compare-with", str(copy)).returncode == 2
    path.write_bytes(b'{"schema_version":1,"schema_version":2}')
    assert run("--profile", "conversation-v6").returncode == 1


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI source proof with PG export")
def test_actual_dpapi_guarded_export(control):
    data = prepare(control, actual=True)
    assert exported(data).bundle["restriction_evidence"]["epoch"] == 0


@pytest.mark.db
def test_exit_migration_preserves_prior_unrelated_checks(roster, database_urls):
    owner = Database(database_urls["migrator"], migration=True, profile="conversation-d1")
    try:
        with owner.transaction() as connection:
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "db/migrations"))
            config.attributes["connection"] = connection
            alembic_command.upgrade(config, "0018")
            before = dict(connection.execute(text("""SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='class_os.command_proposal'::regclass AND contype='c'""")).all())
            exports = dict(connection.execute(text("""SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='class_os.export_job'::regclass AND contype='c'""")).all())
        migrate(owner)
        with owner.transaction(read_only=True) as connection:
            after = dict(connection.execute(text("""SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='class_os.command_proposal'::regclass AND contype='c'""")).all())
            new_exports = dict(connection.execute(text("""SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='class_os.export_job'::regclass AND contype='c'""")).all())
        for key, value in before.items():
            if key not in ("command_proposal_command_type_check", "command_proposal_check1"):
                assert after[key] == value
        for key, value in exports.items():
            if key != "export_job_bundle_check":
                assert new_exports[key] == value
        assert "conversation_exit.create" in after["command_proposal_d1_risk_check"]
    finally:
        owner.close()
