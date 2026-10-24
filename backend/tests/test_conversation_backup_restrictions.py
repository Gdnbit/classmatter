"""Actual disposable clone checks against external current clear restrictions."""
from datetime import timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.conversation_control import ConversationBusinessGateway
from class_os.domain.conversation_control import ClearConversation
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions, FILE_NAME, ClearMarker
from class_os.infrastructure.local_runtime import protect
from class_os.infrastructure.operator_backup import SyntheticBackup, BackupRejected
from class_os.infrastructure.persistence.database import Database
from test_conversation_backup import conversation_runtime, backup_runtime, roster, identity, inventory
from test_operator_backup import fixture_codec


def setup(runtime, roster):
    values = runtime.conversation_values
    port = ProtectedConversationRestrictions(runtime.root, values["workspace"], codec=fixture_codec)
    database = Database(roster[2].database.engine.url, profile="conversation-d1")
    store = ConversationBusinessStore(database, port)
    gateway = ConversationBusinessGateway(roster[4], store, clock=lambda: roster[6][0])
    return port, database, store, gateway


def clear(runtime, roster, gateway):
    values = runtime.conversation_values
    roster[6][0] = values["at"] + timedelta(seconds=2)
    command = ClearConversation(values["thread"], values["class"], values["term"], 1)
    proposal = gateway.preview(*roster[3], command)
    nonce = gateway.approve(*roster[3], proposal.proposal_id, proposal.payload_hash)
    return proposal, nonce


def submit(gateway, roster, prepared):
    proposal, nonce = prepared
    return gateway.commit(*roster[3], proposal.proposal_id, uuid4(), nonce)


def no_clone(runtime):
    with runtime.admin() as connection:
        assert not connection.execute("SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname LIKE 'class_os_synthetic_restore_%')").fetchone()[0]


def test_default_profile_cannot_claim_current_conversation_restrictions():
    with pytest.raises(BackupRejected):
        SyntheticBackup(None).check_current_restrictions(uuid4(), object())


@pytest.mark.db
def test_current_clone_observation_preserves_source_and_packet(conversation_runtime, roster):
    runtime = conversation_runtime
    port, database, _, _ = setup(runtime, roster)
    try:
        backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
        artifact = backup.create()
        path = runtime.root / "backups" / (str(artifact) + ".dpapi")
        original, before = path.read_bytes(), inventory(runtime)
        report = backup.check_current_restrictions(artifact, port)
        assert report["current_restrictions_verified_at_check"] is True and report["observation_only"] is True
        assert report["activation_allowed"] is False and "verified" not in report
        assert "合成checkpoint" not in str(report)
        assert before == inventory(runtime) and path.read_bytes() == original
        assert "current_restrictions_verified_at_check" not in backup.check(artifact)
        no_clone(runtime)
    finally:
        database.close()


@pytest.mark.db
def test_real_bcg_clear_rejects_old_snapshot_but_new_snapshot_matches(conversation_runtime, roster):
    runtime = conversation_runtime
    port, database, _, gateway = setup(runtime, roster)
    try:
        backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
        old = backup.create()
        submit(gateway, roster, clear(runtime, roster, gateway))
        before = inventory(runtime)
        assert backup.check(old)["snapshot_integrity_verified"] is True
        with pytest.raises(BackupRejected):
            backup.check_current_restrictions(old, port)
        new = backup.create()
        assert backup.check_current_restrictions(new, port)["activation_allowed"] is False
        assert inventory(runtime) == before
        no_clone(runtime)
    finally:
        database.close()


@pytest.mark.db
@pytest.mark.parametrize("fault", ["missing", "corrupt", "wrong-workspace", "wrong-root", "proof-dict", "pending"])
def test_bad_current_source_never_creates_clone(conversation_runtime, roster, monkeypatch, tmp_path, fault):
    runtime = conversation_runtime
    port, database, store, gateway = setup(runtime, roster)
    try:
        backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
        artifact = backup.create()
        path = runtime.root / FILE_NAME
        if fault == "missing":
            path.unlink()
        elif fault == "corrupt":
            path.write_bytes(b"synthetic-corrupt")
        elif fault == "wrong-workspace":
            port = ProtectedConversationRestrictions(runtime.root, uuid4(), codec=fixture_codec)
        elif fault == "wrong-root":
            port = ProtectedConversationRestrictions(tmp_path, port.workspace_id, codec=fixture_codec)
        elif fault == "proof-dict":
            port = {"epoch": 0, "current": True}
        else:
            prepared = clear(runtime, roster, gateway)
            with monkeypatch.context() as patch:
                patch.setattr(store, "audit", lambda *args: None)
                with pytest.raises(AuditUnavailable):
                    submit(gateway, roster, prepared)
        def forbidden():
            pytest.fail("Invalid current source must reject before clone allocation")
        monkeypatch.setattr(runtime, "admin", forbidden)
        with pytest.raises(BackupRejected):
            backup.check_current_restrictions(artifact, port)
    finally:
        database.close()


@pytest.mark.db
def test_clear_during_actual_restore_invalidates_observation_and_cleans_clone(conversation_runtime, roster, monkeypatch):
    runtime = conversation_runtime
    port, database, _, gateway = setup(runtime, roster)
    try:
        backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
        artifact = backup.create()
        prepared = clear(runtime, roster, gateway)
        original = backup._pg
        advanced = []
        def restore_then_clear(binary, *args, **kwargs):
            result = original(binary, *args, **kwargs)
            if binary == "pg_restore":
                advanced.append(submit(gateway, roster, prepared))
            return result
        monkeypatch.setattr(backup, "_pg", restore_then_clear)
        with pytest.raises(BackupRejected):
            backup.check_current_restrictions(artifact, port)
        assert len(advanced) == 1 and port.read().head.epoch == 1
        no_clone(runtime)
    finally:
        database.close()


@pytest.mark.db
@pytest.mark.parametrize("fault", ["source-partial-rollback", "clone-partial-rollback", "orphan-marker"])
def test_head_alone_cannot_hide_clear_relation_breakage(conversation_runtime, roster, monkeypatch, fault):
    runtime = conversation_runtime
    port, database, _, gateway = setup(runtime, roster)
    try:
        backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
        submit(gateway, roster, clear(runtime, roster, gateway))
        artifact = backup.create()
        def partial(connection):
            connection.execute(text("""UPDATE class_os.conversation_thread SET status='active',title='合成旧标题',
                version=1,cleared_at=NULL"""))
            connection.execute(text("UPDATE class_os.conversation_message SET visibility='visible',body='合成旧正文'"))
        if fault == "clone-partial-rollback":
            original = backup._pg
            def restore_then_alter(binary, target, *args, **kwargs):
                result = original(binary, target, *args, **kwargs)
                if binary == "pg_restore":
                    clone = Database(database.engine.url.set(database=target), migration=True, profile="conversation-d1")
                    try:
                        with clone.transaction() as connection:
                            partial(connection)
                    finally:
                        clone.close()
                return result
            monkeypatch.setattr(backup, "_pg", restore_then_alter)
        else:
            owner = runtime.database("migrator")
            try:
                with owner.transaction() as connection:
                    if fault == "source-partial-rollback":
                        partial(connection)
                    else:
                        old = port.read()
                        head = port.advance(old.head, ClearMarker(uuid4(), 2, roster[6][0]))
                        connection.execute(text("UPDATE class_os.conversation_control SET epoch=:epoch,head_hash=:hash"),
                                           {"epoch": head.epoch, "hash": head.digest})
            finally:
                owner.close()
        with pytest.raises(BackupRejected):
            backup.check_current_restrictions(artifact, port)
        no_clone(runtime)
    finally:
        database.close()


@pytest.mark.db
@pytest.mark.parametrize("fault", ["restore-failure", "final-proof-corrupt"])
def test_failed_restore_or_final_proof_keeps_source_and_packet_and_removes_clone(conversation_runtime, roster, monkeypatch, fault):
    runtime = conversation_runtime
    port, database, _, _ = setup(runtime, roster)
    try:
        backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
        artifact = backup.create()
        path = runtime.root / "backups" / (str(artifact) + ".dpapi")
        original, before, sealed = backup._pg, inventory(runtime), path.read_bytes()
        def injected(binary, *args, **kwargs):
            if binary == "pg_restore" and fault == "restore-failure":
                raise BackupRejected()
            result = original(binary, *args, **kwargs)
            if binary == "pg_restore":
                (runtime.root / FILE_NAME).write_bytes(b"synthetic-corrupt-at-final-check")
            return result
        monkeypatch.setattr(backup, "_pg", injected)
        with pytest.raises(BackupRejected):
            backup.check_current_restrictions(artifact, port)
        assert inventory(runtime) == before and path.read_bytes() == sealed
        no_clone(runtime)
    finally:
        database.close()


@pytest.mark.db
def test_self_consistent_archive_with_current_head_but_old_visible_rows_is_rejected(conversation_runtime, roster):
    runtime = conversation_runtime
    port, database, _, gateway = setup(runtime, roster)
    owner = runtime.database("migrator")
    try:
        backup = SyntheticBackup(runtime, codec=fixture_codec, profile="conversation-d1")
        submit(gateway, roster, clear(runtime, roster, gateway))
        before = inventory(runtime)
        # Deliberately simulate a partial SQL rollback in a disposable source.
        # Archive/inventory agree; the external marker and retained anchor do
        # not agree with these old thread rows. No hash forgery is involved.
        try:
            with owner.transaction() as connection:
                connection.execute(text("""UPDATE class_os.conversation_thread SET status='active',title='合成旧标题',
                    version=1,cleared_at=NULL"""))
                connection.execute(text("UPDATE class_os.conversation_message SET visibility='visible',body='合成旧正文'"))
            bad = backup.create()
        finally:
            with owner.transaction() as connection:
                connection.execute(text("""UPDATE class_os.conversation_thread SET status='cleared',title='已清除的会话',
                    version=2,cleared_at=:at"""), {"at": roster[6][0]})
                connection.execute(text("UPDATE class_os.conversation_message SET visibility='restricted',body=NULL"))
        assert inventory(runtime) == before
        # The unchanged structural verifier explicitly accepts this snapshot.
        assert backup.check(bad)["snapshot_integrity_verified"] is True
        with pytest.raises(BackupRejected):
            backup.check_current_restrictions(bad, port)
        assert inventory(runtime) == before
        no_clone(runtime)
    finally:
        owner.close()
        database.close()


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI current restriction and checkpoint check")
def test_actual_dpapi_current_restrictions(conversation_runtime, roster):
    runtime = conversation_runtime
    path = runtime.root / FILE_NAME
    path.write_bytes(protect(fixture_codec(path.read_bytes(), decrypt=True)))
    port = ProtectedConversationRestrictions(runtime.root, runtime.conversation_values["workspace"])
    backup = SyntheticBackup(runtime, profile="conversation-d1")
    artifact = backup.create()
    assert backup.check_current_restrictions(artifact, port)["current_restrictions_verified_at_check"] is True
    no_clone(runtime)
