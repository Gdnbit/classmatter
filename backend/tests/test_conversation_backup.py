"""Actual D1 checkpoint clones; snapshot checks never authorize activation."""
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.infrastructure.operator_backup import SyntheticBackup, BackupRejected
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.schema_inventory import schema_profile
from class_os.infrastructure.conversation_integrity import validate_conversation_integrity
from test_operator_backup import backup_runtime, fixture_codec, roster, identity
from test_durable_conversation_storage import thread, turn, queued, message
from class_os.application.conversation_control import ConversationBusinessGateway
from class_os.domain.conversation_control import InitializeConversationControl
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions


@pytest.fixture
def conversation_runtime(backup_runtime, roster, database_urls):
    owner = Database(database_urls["migrator"], migration=True, profile="conversation-d1")
    try:
        migrate(owner)
        runtime = Database(database_urls["runtime"], profile="conversation-d1")
        try:
            controls = ProtectedConversationRestrictions(backup_runtime.root, roster[3][3], codec=fixture_codec)
            gateway = ConversationBusinessGateway(roster[4], ConversationBusinessStore(runtime, controls), clock=lambda: roster[6][0])
            proposal = gateway.preview(*roster[3], InitializeConversationControl(uuid4()))
            nonce = gateway.approve(*roster[3], proposal.proposal_id, proposal.payload_hash)
            gateway.commit(*roster[3], proposal.proposal_id, uuid4(), nonce)
        finally:
            runtime.close()
        with owner.transaction() as connection:
            row = connection.execute(text("""SELECT e.workspace_id AS workspace,o.owner_id AS owner,
                e.class_id AS class,e.term_id AS term,e.student_id AS student,e.enrollment_id AS enrollment
                FROM class_os.enrollment e JOIN class_os.owner_account o USING(workspace_id)""")).mappings().one()
            values = {**row, "at": roster[6][0], "thread": uuid4(), "turn": uuid4(), "run": uuid4(), "key": uuid4()}
            thread(connection, values)
            turn(connection, values)
            queued(connection, values)
            message(connection, values, body="合成checkpoint用户原文")
            connection.execute(text("""UPDATE class_os.conversation_run SET state='running',version=2,
                generation=:generation,started_at=:at,lease_until=:at+interval '1 minute'"""),
                {**values, "generation": uuid4()})
            connection.execute(text("""UPDATE class_os.conversation_run SET state='completed',version=3,
                ended_at=:at+interval '1 second'"""), values)
            message(connection, values, role="assistant", origin="assistant-unverified", body="合成checkpoint未核实草稿")
        backup_runtime.conversation_values = values
        return backup_runtime
    finally:
        owner.close()


def inventory(runtime):
    owner = runtime.database("migrator")
    try:
        with owner.transaction(read_only=True) as connection:
            return SyntheticBackup._inventory(connection, profile="conversation-d1")
    finally:
        owner.close()


def test_unknown_checkpoint_profile_is_rejected_without_runtime_access():
    for profile in ("unknown", "conversation-d1 ", None, {}):
        with pytest.raises(ValueError):
            SyntheticBackup(None, profile=profile)


@pytest.mark.db
def test_real_d1_snapshot_clone_verifies_all_tables_without_activation_or_source_mutation(conversation_runtime):
    runtime = conversation_runtime
    before = inventory(runtime)
    backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
    artifact = backup.create()
    packet, _ = backup._open(artifact)
    assert packet["kind"] == "classmatter.owned-conversation-backup.v1"
    assert packet["schema_profile"] == "conversation-d1" and packet["activation_allowed"] is False
    assert packet["head"] == schema_profile("conversation-d1")[0]
    assert packet["inventory"] == before and len(before) == 27
    assert all(before[table]["rows"] == count for table, count in
               (("conversation_thread", 1), ("conversation_turn", 1), ("conversation_message", 2), ("conversation_run", 1)))
    path = runtime.root / "backups" / (str(artifact) + ".dpapi")
    sealed = path.read_bytes()
    report = backup.check(artifact)
    assert report == {"schema_version": "classmatter.conversation-backup-check.v1",
                      "snapshot_integrity_verified": True, "activation_allowed": False,
                      "source_preserved": True, "temporary_clone_removed": True, "portable": False,
                      "complete_exit": False, "table_count": 27}
    assert "合成checkpoint" not in json.dumps(report)
    assert inventory(runtime) == before and path.read_bytes() == sealed
    assert backup.catalog()["activation_allowed"] is False
    assert backup.catalog()["checkpoints"][0]["restore_verified"] is False
    with runtime.admin() as root:
        assert not root.execute("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname LIKE 'class_os_synthetic_restore_%')").fetchone()[0]
    # An old reader cannot silently call this a core-only checkpoint.
    with pytest.raises(BackupRejected):
        SyntheticBackup(runtime, codec=fixture_codec).check(artifact)
    with pytest.raises(BackupRejected):
        SyntheticBackup(runtime, codec=fixture_codec).create()


@pytest.mark.db
@pytest.mark.parametrize("fault", ["profile", "head", "activation", "inventory", "unknown-field"])
def test_changed_packet_metadata_never_creates_clone_or_claims_activation(conversation_runtime, monkeypatch, fault):
    runtime = conversation_runtime
    backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
    artifact = backup.create()
    packet, _ = backup._open(artifact)
    path = runtime.root / "backups" / (str(artifact) + ".dpapi")
    if fault == "profile":
        packet["schema_profile"] = "r1"
    elif fault == "head":
        packet["head"] = "0016"
    elif fault == "activation":
        packet["activation_allowed"] = True
    elif fault == "inventory":
        packet["inventory"].pop("conversation_message")
    else:
        packet["provider-run"] = "must-not-resume"
    # Fixture codec permits tampering to exercise schema validation; this is
    # not a cryptographic claim about DPAPI.
    path.write_bytes(fixture_codec(json.dumps(packet).encode()))
    def forbidden():
        pytest.fail("Invalid packet must not open administrator or create a clone")
    monkeypatch.setattr(runtime, "admin", forbidden)
    with pytest.raises(BackupRejected):
        backup.check(artifact)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["missing-user", "missing-assistant", "failed-with-assistant", "missing-run", "cleared-visible", "partial-restriction", "archived-active"])
def test_aggregate_inconsistency_blocks_snapshot_publication(conversation_runtime, fault):
    runtime = conversation_runtime
    owner = runtime.database("migrator")
    try:
        with owner.transaction() as connection:
            if fault == "missing-user":
                connection.execute(text("DELETE FROM class_os.conversation_message WHERE role='user'"))
            elif fault == "missing-assistant":
                connection.execute(text("DELETE FROM class_os.conversation_message WHERE role='assistant'"))
            elif fault == "failed-with-assistant":
                connection.execute(text("UPDATE class_os.conversation_run SET state='failed'"))
            elif fault == "missing-run":
                connection.execute(text("DELETE FROM class_os.conversation_run"))
            elif fault == "cleared-visible":
                connection.execute(text("""UPDATE class_os.conversation_thread SET title='已清除的会话',status='cleared',
                    cleared_at=:at,updated_at=:at"""), runtime.conversation_values)
            elif fault == "partial-restriction":
                connection.execute(text("UPDATE class_os.conversation_message SET visibility='restricted',body=NULL WHERE role='user'"))
            else:
                # Replace the terminal fixture with a valid running row while
                # retaining no assistant answer. It must not live in archive.
                connection.execute(text("DELETE FROM class_os.conversation_message WHERE role='assistant'"))
                connection.execute(text("UPDATE class_os.conversation_run SET state='running',ended_at=NULL"))
                connection.execute(text("UPDATE class_os.conversation_thread SET status='archived'"))
        before = inventory(runtime)
        backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
        with pytest.raises(BackupRejected):
            backup.create()
        assert inventory(runtime) == before
        assert not (runtime.root / "backups").exists()
    finally:
        owner.close()


@pytest.mark.db
def test_consistent_restriction_is_preserved_and_live_run_snapshot_is_never_resumed(conversation_runtime):
    runtime = conversation_runtime
    backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
    old = backup.create()
    owner = runtime.database("migrator")
    try:
        with owner.transaction() as connection:
            connection.execute(text("UPDATE class_os.conversation_message SET visibility='restricted',body=NULL"))
            connection.execute(text("""UPDATE class_os.conversation_thread SET title='已清除的会话',status='cleared',
                cleared_at=:at,updated_at=:at"""), runtime.conversation_values)
            validate_conversation_integrity(connection)
        cleared = inventory(runtime)
        # An old snapshot may still be structurally valid. It never acquires
        # activation authority and cannot roll source content back by checking.
        old_report = backup.check(old)
        assert old_report["snapshot_integrity_verified"] is True and old_report["activation_allowed"] is False
        assert inventory(runtime) == cleared
        artifact = backup.create()
        assert backup._open(old)[0]["inventory"]["conversation_message"] != backup._open(artifact)[0]["inventory"]["conversation_message"]
        assert backup.check(artifact)["activation_allowed"] is False
        with owner.transaction() as connection:
            second = {**runtime.conversation_values, "thread": uuid4(), "turn": uuid4(), "run": uuid4(), "key": uuid4()}
            thread(connection, second)
            turn(connection, second)
            queued(connection, second)
            message(connection, second)
        active = backup.create()
        assert backup.check(active)["activation_allowed"] is False
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT state FROM class_os.conversation_run WHERE run_id=:run"), second).scalar_one() == "queued"
    finally:
        owner.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Actual current-user Windows DPAPI")
def test_d1_actual_dpapi_does_not_publish_plaintext_and_rejects_corruption(conversation_runtime):
    backup = SyntheticBackup(conversation_runtime, profile="conversation-d1")
    artifact = backup.create()
    path = conversation_runtime.root / "backups" / (str(artifact) + ".dpapi")
    sealed = path.read_bytes()
    assert b'"inventory"' not in sealed and b"PGDMP" not in sealed
    assert backup.check(artifact)["snapshot_integrity_verified"] is True
    path.write_bytes(sealed[:-1] + bytes([sealed[-1] ^ 1]))
    with pytest.raises(BackupRejected):
        backup.check(artifact)


@pytest.mark.db
def test_matching_hashes_do_not_hide_widened_clone_acl_and_clone_is_removed(conversation_runtime, monkeypatch):
    runtime = conversation_runtime
    backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
    artifact = backup.create()
    before = inventory(runtime)
    original = backup._pg
    targets = []
    def alter_clone(binary, database, *args, **kwargs):
        result = original(binary, database, *args, **kwargs)
        if binary == "pg_restore":
            source = runtime.database("migrator")
            clone = Database(source.engine.url.set(database=database), migration=True, profile="conversation-d1")
            try:
                with clone.transaction() as connection:
                    connection.execute(text("GRANT UPDATE(origin) ON class_os.conversation_message TO class_os_runtime"))
                targets.append(database)
            finally:
                source.close()
                clone.close()
        return result
    monkeypatch.setattr(backup, "_pg", alter_clone)
    with pytest.raises(BackupRejected):
        backup.check(artifact)
    assert len(targets) == 1 and inventory(runtime) == before
    with runtime.admin() as root:
        assert not root.execute("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s)", (targets[0],)).fetchone()[0]
