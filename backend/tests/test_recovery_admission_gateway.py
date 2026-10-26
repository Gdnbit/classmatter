"""Actual two-Owner PG retirement, admission, edits, clear and recovery evidence."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import os
import subprocess
import tempfile

import psycopg
import pytest
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.roster import CommandRejected, QueryGateway
from class_os.application.conversation_control import ConversationQueryGateway
from class_os.application.recovery_admission import AdmissionGateway, AdmissionQueryGateway, AuthorizedRetirementReader
from class_os.domain.activity import CreateRecord, CreateTask, ReviseRecord, ChangeTask
from class_os.domain.roster import ChangeStudentName
from class_os.domain.conversation_control import ClearConversation
from class_os.domain.conversation_exit import CreateConversationExit
from class_os.domain.conversation_exit_v6 import validate_v6
from class_os.domain.recovery_admission import AdmitConversationTarget
from class_os.infrastructure.recovery_admission import ProtectedTargetAdmission, FILE_NAME
from class_os.infrastructure.recovery_admission_store import AdmissionStore, AdmissionTransaction
from class_os.infrastructure.target_import import FILE_NAME as IMPORT_FILE
from class_os.infrastructure.source_retirement import FILE_NAME as RETIREMENT_FILE
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from class_os.infrastructure.persistence.database import Database
from class_os.infrastructure.persistence.role_guards import validate_role_guards
from class_os.infrastructure.operator_backup import SyntheticBackup
from test_source_retirement_gateway import (world, target, control, storage, roster, identity,
    retirement, approve_retirement, commit_retirement)
from test_target_import_gateway import prepare, approved, commit
from test_conversation_control import commit as control_commit
from test_durable_conversation_storage import message
from test_model_secrets import fixture_codec


def ready(world, target, *, with_facts=False, assistant=False, legacy_no_receipt=False):
    values = world[5]
    record, task = None, None
    if with_facts:
        record = CreateRecord("record.create", uuid4(), values["class"], values["term"], values["student"],
                              "ordinary_fact", world[7][0], "合成恢复前事实", "合成观察不等于事实")
        control_commit(world, record)
        task = CreateTask("task.create", uuid4(), values["class"], values["term"], "合成恢复前任务",
                          student_id=values["student"], source_record_id=record.record_id)
        control_commit(world, task)
    if assistant:
        # Replace this fixture's raw, never-dispatched seed with an actual legacy
        # BCG completion. v6 must not invent provenance for an unaudited reply.
        with world[4].transaction() as connection:
            for table in ("conversation_message", "conversation_run", "conversation_turn", "conversation_thread"):
                assert connection.execute(text("DELETE FROM class_os." + table + " WHERE workspace_id=:workspace AND thread_id=:thread"), values).rowcount == 1
        from class_os.application.conversation_worker import ConversationWorkerGateway
        worker = ConversationWorkerGateway(world[0].identity, AdmissionStore(world[2].database, world[3]), clock=world[0].clock)
        worker.create_conversation(*world[6], values["class"], values["term"], values["thread"], uuid4(), "synthetic legacy BCG conversation", values["student"])
        key = uuid4()
        worker.enqueue(*world[6], values["class"], values["term"], values["thread"], key, "synthetic legacy input", "chat")
        ticket = worker.claim(world[6], values["class"], values["term"], values["thread"], key)
        worker.finish_run(world[6], ticket, "completed", "合成AI解释仍未核实")
        if legacy_no_receipt:
            with world[4].transaction() as connection:
                assert connection.execute(text("DELETE FROM class_os.conversation_result_receipt")).rowcount == 1
            world[7][0] += timedelta(seconds=1)
    data = prepare(world, target, terminal=not assistant)
    imported = commit(data, approved(data))
    _, source, query, command, stage = retirement(world, data)
    retired = commit_retirement(world, source, approve_retirement(world, source, command))
    proof = query.committed_retirement(*world[6], command.attempt_id)
    reader = AuthorizedRetirementReader(query, world[6], command.attempt_id)
    store = AdmissionStore(data.dbs["runtime"], data.restrictions, reader)
    gateway = AdmissionGateway(data.identity, store, clock=lambda: data.clock[0])
    target_query = AdmissionQueryGateway(data.identity, store, clock=lambda: data.clock[0])
    summary = target_query.admission_summary(*data.credentials, command.attempt_id)
    admit = AdmitConversationTarget(command.attempt_id, proof.proof_hash, summary.stage_hash, summary.origins_hash)
    return SimpleNamespace(data=data, store=store, gateway=gateway, query=target_query, command=admit,
                           source=query, imported=imported, retired=retired, summary=summary, record=record, task=task)


def approve(value):
    proposal = value.gateway.preview(*value.data.credentials, value.command)
    assert proposal.risk == "X"
    nonce = value.gateway.approve(*value.data.credentials, proposal.proposal_id, proposal.payload_hash)
    return proposal, nonce


def submit(value, prepared, key=None):
    proposal, nonce = prepared
    return value.gateway.commit(*value.data.credentials, proposal.proposal_id, key or uuid4(), nonce)


def native(value, command):
    proposal = value.gateway.preview(*value.data.credentials, command)
    nonce = value.gateway.approve(*value.data.credentials, proposal.proposal_id, proposal.payload_hash) if proposal.risk != "W1" else None
    return value.gateway.commit(*value.data.credentials, proposal.proposal_id, uuid4(), nonce)


def checkpoint(value):
    data = value.data
    class Runtime:
        root = data.restrictions.root
        def configuration(self):
            binaries = data.binaries / "bin" if (data.binaries / "bin").is_dir() else data.binaries
            return {"profile": "class-os-owned-synthetic-v1", "pg_bin": str(binaries),
                    "port": data.cluster["port"], "database": data.name}
        def password(self, role):
            assert role == "migrator"
            return ""
        def database(self, role):
            assert role == "migrator"
            return Database(data.dbs[role].engine.url, migration=True, profile="conversation-d1")
        @contextmanager
        def admin(self):
            with psycopg.connect(**data.cluster, autocommit=True) as connection:
                yield connection
    return SyntheticBackup(Runtime(), codec=fixture_codec, profile="conversation-d1")


def restart_owned_cluster(data):
    with psycopg.connect(**data.cluster, autocommit=True) as root:
        directory = Path(root.execute("SHOW data_directory").fetchone()[0]).resolve()
        before = root.execute("SELECT pg_postmaster_start_time()").fetchone()[0]
    assert data.cluster["user"] == "class_os_test_root"
    assert directory.name == "cluster" and directory.parent.name.startswith("class-os-test-pg-")
    assert directory.parent.parent == Path(tempfile.gettempdir()).resolve()
    binaries = data.binaries / "bin" if (data.binaries / "bin").is_dir() else data.binaries
    binary = binaries / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")
    result = subprocess.run([str(binary), "-D", str(directory), "restart", "-m", "fast", "-w", "-t", "30"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0
    with psycopg.connect(**data.cluster, autocommit=True) as root:
        assert root.execute("SELECT pg_postmaster_start_time()").fetchone()[0] > before


@pytest.mark.db
def test_real_admission_native_edits_attribution_clear_restart_checkpoint_and_v5(world, target):
    value = ready(world, target, with_facts=True, assistant=True)
    prepared, key = approve(value), uuid4()
    with pytest.raises(CommandRejected):
        value.gateway.commit(*value.data.credentials, prepared[0].proposal_id, key)
    receipt = submit(value, prepared, key)
    assert receipt.version == 3 and submit(value, prepared, key) == receipt
    assert value.query.command_status(*value.data.credentials, prepared[0].proposal_id, key).receipt == receipt
    ids, credentials = world[5], value.data.credentials
    history = value.query.conversation_history(*credentials, ids["class"], ids["term"], ids["thread"])
    human, assistant = history.message_attributions
    assert human["attribution"]["created_by"] == str(ids["owner"])
    assert assistant["attribution"]["created_by"] is None and assistant["attribution"]["content_authority"] == "assistant-unverified"
    activity = value.query.projection(*credentials, ids["class"], ids["term"])
    assert activity["records"][0]["attribution"]["created_by"] == str(ids["owner"])
    assert activity["tasks"][0]["attribution"]["created_by"] == str(ids["owner"])
    # Old body readers may not silently strip source/author metadata.
    with pytest.raises(CommandRejected):
        QueryGateway(value.data.identity, value.store, clock=lambda: value.data.clock[0]).projection(*credentials, ids["class"], ids["term"])
    with pytest.raises(CommandRejected):
        ConversationQueryGateway(value.data.identity, ConversationBusinessStore(value.data.dbs["runtime"], value.data.restrictions),
                                 clock=lambda: value.data.clock[0]).conversation_history(*credentials, ids["class"], ids["term"], ids["thread"])
    # Admission no longer depends on a usable source session/service.
    world[0].identity.logout(*world[6][:3])
    value.data.clock[0] += timedelta(seconds=1)
    original_name = value.query.roster(*credentials, ids["class"], ids["term"])[0].name
    native(value, ChangeStudentName("student.update_name", ids["student"], ids["class"], ids["term"], 1, original_name, "合成恢复后更名"))
    native(value, ReviseRecord("record.correct", value.record.record_id, ids["class"], ids["term"], 1,
                              "合成本地事实更正", "合成本地观察", "合成人工修订"))
    native(value, ChangeTask("task.update", value.task.task_id, ids["class"], ids["term"], 1, "waiting", "合成等待对方", title="合成恢复后任务"))
    activity = value.query.projection(*credentials, ids["class"], ids["term"])
    revisions = {row["version"]: row for row in activity["records"]}
    assert revisions[1]["attribution"]["created_by"] == str(ids["owner"])
    assert revisions[2]["attribution"]["created_by"] == str(value.data.owner)
    task = activity["tasks"][0]
    assert task["attribution"]["created_by"] == str(ids["owner"])
    assert task["attribution"]["last_modified_by"] == str(value.data.owner) and task["version"] == 2
    native(value, ClearConversation(ids["thread"], ids["class"], ids["term"], history.history.version))
    history = value.query.conversation_history(*credentials, ids["class"], ids["term"], ids["thread"])
    assert history.history.status == "cleared" and not history.history.messages
    restart_owned_cluster(value.data)
    reopened = Database(value.data.dbs["runtime"].engine.url, profile="conversation-d1")
    try:
        store = AdmissionStore(reopened, value.data.restrictions)  # No peer/candidate retained.
        query = AdmissionQueryGateway(value.data.identity, store, clock=lambda: value.data.clock[0])
        assert query.roster(*credentials, ids["class"], ids["term"])[0].name == "合成恢复后更名"
        assert query.projection(*credentials, ids["class"], ids["term"])["records"] == activity["records"]
        assert not query.conversation_history(*credentials, ids["class"], ids["term"], ids["thread"]).history.messages
    finally:
        reopened.close()
    backup = checkpoint(value)
    artifact = backup.create()
    checked = backup.check_current_restrictions(artifact, value.data.restrictions)
    assert checked["activation_allowed"] is False and checked["table_count"] == 35
    summary = value.query.conversation_exit_summary(*credentials)
    export = CreateConversationExit(uuid4(), summary.snapshot_hash)
    native(value, export)
    bundle = value.query.conversation_exit_download(*credentials, export.export_id).bundle
    assert validate_v6(bundle) and bundle["activation_allowed"] is False
    assert all(row["body"] is None for row in bundle["conversations"]["conversation_message"])
    assert not any("body" in row for row in bundle["recovery"]["conversation_origin"])
    with value.data.dbs["migrator"].transaction(read_only=True) as connection:
        validate_role_guards(connection, profile="conversation-d1")
        assert connection.execute(text("SELECT count(*) FROM class_os.owner_account")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 2


@pytest.mark.db
@pytest.mark.parametrize("fault", ["audit", "finish", "late-validation"])
def test_file_first_admission_rolls_back_sql_and_retries_same_attempt(world, target, monkeypatch, fault):
    value = ready(world, target)
    prepared, key = approve(value), uuid4()
    with monkeypatch.context() as patch:
        if fault == "audit":
            patch.setattr(value.store, "audit", lambda *args: None)
            error = AuditUnavailable
        elif fault == "finish":
            patch.setattr(AdmissionTransaction, "finish", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic SQL failure")))
            error = RuntimeError
        else:
            original = AdmissionTransaction._snapshot
            def reject_after_insert(self, binding, now):
                if self.has_committed_admission(binding):
                    raise CommandRejected()
                return original(self, binding, now)
            patch.setattr(AdmissionTransaction, "_snapshot", reject_after_insert)
            error = RuntimeError
        with pytest.raises(error):
            submit(value, prepared, key)
    assert ProtectedTargetAdmission(value.data.restrictions).present()
    with value.data.dbs["migrator"].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_admission")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_origin")).scalar_one() == 0
    with pytest.raises(CommandRejected):
        value.query.context(*value.data.credentials)
    result = submit(value, prepared, key)
    assert value.query.command_status(*value.data.credentials, prepared[0].proposal_id, key).receipt == result


@pytest.mark.db
def test_gateway_name_never_substitutes_for_author_aware_transaction(world, target):
    value = ready(world, target)
    plain = ConversationBusinessStore(value.data.dbs["runtime"], value.data.restrictions)
    wrong = AdmissionGateway(value.data.identity, plain, clock=lambda: value.data.clock[0])
    with pytest.raises(CommandRejected):
        wrong.preview(*value.data.credentials, value.command)
    submit(value, approve(value))
    wrong_query = AdmissionQueryGateway(value.data.identity, plain, clock=lambda: value.data.clock[0])
    ids = world[5]
    with pytest.raises(CommandRejected):
        wrong_query.projection(*value.data.credentials, ids["class"], ids["term"])
    with pytest.raises(CommandRejected):
        wrong_query.conversation_history(*value.data.credentials, ids["class"], ids["term"], ids["thread"])
    with pytest.raises(CommandRejected):
        wrong.preview(*value.data.credentials, ClearConversation(ids["thread"], ids["class"], ids["term"], 1))


@pytest.mark.db
@pytest.mark.parametrize("fault", ["batch", "source-audit", "origin", "body", "file-missing", "file-corrupt", "file-directory", "receipt", "audit", "stage-receipt", "stage-audit", "stage-payload"])
def test_admitted_corruption_denies_reads_writes_and_exit(world, target, fault):
    value = ready(world, target)
    submit(value, approve(value))
    path = value.data.restrictions.root / FILE_NAME
    if fault.startswith("file-"):
        if fault == "file-corrupt":
            path.write_bytes(b"synthetic-corrupt")
        else:
            path.unlink()
            if fault == "file-directory":
                path.mkdir()
    else:
        with value.data.dbs["migrator"].transaction() as connection:
            statements = {
                "batch": "UPDATE class_os.conversation_import SET package_hash=repeat('0',64)",
                "source-audit": "DELETE FROM class_os.conversation_source_audit",
                "origin": "UPDATE class_os.conversation_origin SET identity_hash=repeat('0',64)",
                "body": "UPDATE class_os.conversation_message SET body='synthetic substituted body'",
                "receipt": "DELETE FROM class_os.command_receipt WHERE resource_version=3",
                "audit": "DELETE FROM class_os.business_audit WHERE receipt_id IN (SELECT receipt_id FROM class_os.command_receipt WHERE resource_version=3) AND action='command.commit'",
                "stage-receipt": "DELETE FROM class_os.command_receipt WHERE resource_version=1 AND resource_id IN (SELECT attempt_id FROM class_os.conversation_import)",
                "stage-audit": "DELETE FROM class_os.business_audit WHERE action='command.commit' AND proposal_id IN (SELECT proposal_id FROM class_os.command_proposal WHERE command_type='conversation.import.stage')",
                "stage-payload": "UPDATE class_os.command_proposal SET payload=jsonb_set(payload,'{package_hash}',to_jsonb(repeat('0',64))) WHERE command_type='conversation.import.stage'",
            }
            result = connection.execute(text(statements[fault]))
            assert result.rowcount > 0
    ids = world[5]
    for query in (lambda: value.query.context(*value.data.credentials),
                  lambda: value.query.projection(*value.data.credentials, ids["class"], ids["term"]),
                  lambda: value.query.conversation_history(*value.data.credentials, ids["class"], ids["term"], ids["thread"]),
                  lambda: value.query.conversation_exit_summary(*value.data.credentials),
                  lambda: value.gateway.preview(*value.data.credentials, ClearConversation(ids["thread"], ids["class"], ids["term"], 1))):
        with pytest.raises(CommandRejected):
            query()


@pytest.mark.db
@pytest.mark.parametrize("command_type", ["conversation.transfer.seal", "conversation.import.stage", "conversation.transfer.retire"])
def test_missing_original_commit_audit_denies_admission(world, target, command_type):
    value = ready(world, target)
    database = value.data.dbs["migrator"] if command_type == "conversation.import.stage" else world[4]
    with database.transaction() as connection:
        removed = connection.execute(text("""DELETE FROM class_os.business_audit WHERE action='command.commit'
            AND proposal_id IN (SELECT proposal_id FROM class_os.command_proposal WHERE command_type=:command)"""),
            {"command": command_type})
        assert removed.rowcount == 1
    with pytest.raises(CommandRejected):
        value.gateway.preview(*value.data.credentials, value.command)
    assert not ProtectedTargetAdmission(value.data.restrictions).present()


@pytest.mark.db
def test_capacity_is_checked_before_source_retirement(world, target, monkeypatch):
    data = prepare(world, target)
    commit(data, approved(data))
    store, gateway, query, command, stage = retirement(world, data)
    from class_os.infrastructure import target_import_store
    original = target_import_store.validate_projection_budget
    def oversized(connection, projected):
        if projected[3]["conversation_admission"]:
            raise CommandRejected()
        return original(connection, projected)
    monkeypatch.setattr(target_import_store, "validate_projection_budget", oversized)
    with pytest.raises(CommandRejected):
        approve_retirement(world, gateway, command)
    assert not (world[3].root / RETIREMENT_FILE).exists()
    assert not ProtectedTargetAdmission(data.restrictions).present()


@pytest.mark.db
def test_file_only_admission_plus_preimport_sql_rollback_stays_quarantined(world, target, monkeypatch):
    value = ready(world, target)
    prepared = approve(value)
    with monkeypatch.context() as patch:
        patch.setattr(AdmissionTransaction, "finish", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic rollback")))
        with pytest.raises(RuntimeError):
            submit(value, prepared)
    assert ProtectedTargetAdmission(value.data.restrictions).present()
    with value.data.dbs["migrator"].transaction() as connection:
        connection.execute(text("DELETE FROM class_os.conversation_source_audit"))
        connection.execute(text("DELETE FROM class_os.conversation_provenance"))
        connection.execute(text("DELETE FROM class_os.conversation_import"))
    (value.data.restrictions.root / IMPORT_FILE).unlink()
    with pytest.raises(CommandRejected):
        value.query.context(*value.data.credentials)


@pytest.mark.db
def test_wrong_binding_stale_auth_and_concurrent_admission(world, target):
    value = ready(world, target)
    for fields in ({"attempt_id": uuid4()}, {"expected_stage_hash": "0" * 64},
                   {"expected_retirement_hash": "0" * 64}, {"expected_origins_hash": "0" * 64}):
        with pytest.raises(CommandRejected):
            value.gateway.preview(*value.data.credentials, replace(value.command, **fields))
    assert not ProtectedTargetAdmission(value.data.restrictions).present()
    before = value.data.clock[0]
    value.data.clock[0] += timedelta(minutes=6)
    with pytest.raises(CommandRejected):
        approve(value)
    value.data.clock[0] = before
    prepared, key = approve(value), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(value, prepared, key), range(2)))
    assert results[0] == results[1] and results[0].version == 3
    with pytest.raises(CommandRejected):
        value.gateway.preview(*value.data.credentials, value.command)
    with value.data.dbs["migrator"].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_admission")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.command_receipt WHERE resource_version=3")).scalar_one() == 1
