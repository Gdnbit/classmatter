"""Two fresh disposable databases, actual ISB/BCG and target isolation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4
import os

import psycopg
from psycopg import sql
from pwdlib import PasswordHash
import pytest
from sqlalchemy import text

from class_os.application.audit import AuditUnavailable
from class_os.application.identity import IdentityBoundary, IdentityDenied
from class_os.application.roster import BusinessGateway, QueryGateway, CommandRejected
from class_os.application.conversation_control import ConversationBusinessGateway, ConversationQueryGateway
from class_os.application.source_transfer import SourceTransferGateway, SourceTransferQueryGateway
from class_os.application.target_import import TargetImportGateway, TargetImportQueryGateway, AuthorizedSourceReader
from class_os.domain.conversation_control import InitializeConversationControl, ClearConversation
from class_os.domain.source_transfer import SealConversationSource
from class_os.domain.target_import import RecoveryCandidate, StageConversationImport, IMPORT_COLUMNS
from class_os.domain.roster import CreateClass
from class_os.infrastructure.identity import PostgresIdentityStore
from class_os.infrastructure.conversation_control import ConversationBusinessStore
from class_os.infrastructure.source_transfer_store import SourceTransferStore
from class_os.infrastructure.target_import_store import TargetImportStore, TargetImportTransaction
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions, FILE_NAME as RESTRICTION_FILE
from class_os.infrastructure.target_import import ProtectedTargetImport, FILE_NAME
from class_os.infrastructure.operator_backup import SyntheticBackup
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.role_guards import validate_role_guards
from test_identity import setup, CLIENT
from test_model_secrets import fixture_codec
from test_conversation_exit_gateway import world, control, storage, roster, identity, exported
from test_conversation_control import commit as control_commit
from test_durable_conversation_storage import thread, turn, queued, message
from test_roster_gateway import class_command


@pytest.fixture
def target(world, postgres_cluster, tmp_path, request):
    name = "class_os_synthetic_" + uuid4().hex
    with psycopg.connect(**postgres_cluster, autocommit=True) as root:
        root.execute(sql.SQL("CREATE DATABASE {} OWNER class_os_migrator").format(sql.Identifier(name)))
    dbs = {role: Database(world[4].engine.url.set(username="class_os_" + role, database=name),
                         migration=role == "migrator", identity=role == "identity", profile="conversation-d1")
           for role in ("migrator", "identity", "runtime")}
    try:
        migrate(dbs["migrator"])
        clock = world[7]
        boundary = IdentityBoundary(PostgresIdentityStore(dbs["identity"]), PasswordHash.recommended(), clock=lambda: clock[0])
        auth = setup(boundary)
        credentials = (auth.token, CLIENT, auth.csrf, auth.subject.workspace_id)
        root_path = tmp_path / "target-owned"
        root_path.mkdir()
        from class_os.infrastructure.local_runtime import protect
        codec = protect if getattr(request, "param", False) else fixture_codec
        restrictions = ProtectedConversationRestrictions(root_path, auth.subject.workspace_id, codec=codec)
        initial_store = ConversationBusinessStore(dbs["runtime"], restrictions)
        initial = ConversationBusinessGateway(boundary, initial_store, clock=lambda: clock[0])
        init = initial.preview(*credentials, InitializeConversationControl(uuid4()))
        nonce = initial.approve(*credentials, init.proposal_id, init.payload_hash)
        initial.commit(*credentials, init.proposal_id, uuid4(), nonce)
        yield SimpleNamespace(dbs=dbs, identity=boundary, credentials=credentials, restrictions=restrictions,
                              owner=auth.subject.owner_id, clock=clock, name=name, cluster=postgres_cluster,
                              binaries=Path(request.config.getoption("--pg-root")))
    finally:
        for database in dbs.values():
            database.close()
        with psycopg.connect(**postgres_cluster, autocommit=True) as root:
            root.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def prepare(world, target, *, terminal=True):
    # The fixture represents a never-dispatched cancelled source run.
    if terminal:
        with world[4].transaction() as connection:
            connection.execute(text("UPDATE class_os.conversation_run SET state='cancelled',version=2,ended_at=created_at"))
    artifact = exported(world)
    store = SourceTransferStore(world[2].database, world[3])
    source = SourceTransferGateway(world[0].identity, store, clock=world[0].clock)
    query = SourceTransferQueryGateway(source.identity, store, clock=source.clock)
    command = SealConversationSource(uuid4(), artifact.export_id, artifact.package_hash, target.credentials[3], target.owner,
                                    target.restrictions._binding(target.restrictions._root()))
    proposal = source.preview(*world[6], command)
    nonce = source.approve(*world[6], proposal.proposal_id, proposal.payload_hash)
    source.commit(*world[6], proposal.proposal_id, uuid4(), nonce)
    proof = query.committed_source(*world[6], command.attempt_id)
    candidate = RecoveryCandidate.from_bundle(artifact.bundle)
    importer = TargetImportStore(target.dbs["runtime"], target.restrictions, candidate,
                                 AuthorizedSourceReader(query, world[6], command.attempt_id))
    target.store = importer
    target.gateway = TargetImportGateway(target.identity, importer, clock=lambda: target.clock[0])
    target.query = TargetImportQueryGateway(target.identity, importer, clock=lambda: target.clock[0])
    target.command = StageConversationImport(command.attempt_id, artifact.package_hash, proof.fence_hash)
    target.artifact, target.source = artifact, query
    return target


def approved(data):
    proposal = data.gateway.preview(*data.credentials, data.command)
    assert proposal.risk == "X"
    nonce = data.gateway.approve(*data.credentials, proposal.proposal_id, proposal.payload_hash)
    return proposal, nonce


def commit(data, prepared, key=None):
    proposal, nonce = prepared
    return data.gateway.commit(*data.credentials, proposal.proposal_id, key or uuid4(), nonce)


def counts(data):
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        return {k: connection.execute(text("SELECT count(*) FROM class_os." + k)).scalar_one()
                for k in (*IMPORT_COLUMNS, "academic_term", "student", "conversation_message", "conversation_run")}


def ordinary_denied(data):
    store = ConversationBusinessStore(data.dbs["runtime"], data.restrictions)
    with pytest.raises(CommandRejected):
        ConversationQueryGateway(data.identity, store, clock=lambda: data.clock[0]).context(*data.credentials)
    with pytest.raises(CommandRejected):
        QueryGateway(data.identity, data.store, clock=lambda: data.clock[0]).context(*data.credentials)


@pytest.mark.db
def test_actual_typed_import_replays_receipt_and_never_opens_target(world, target):
    data = prepare(world, target)
    prepared, key = approved(data), uuid4()
    with pytest.raises(CommandRejected):
        data.gateway.commit(*data.credentials, prepared[0].proposal_id, key)
    receipt = commit(data, prepared, key)
    assert receipt.resource_id == data.command.attempt_id
    assert commit(data, prepared, key) == receipt
    assert data.query.command_status(*data.credentials, prepared[0].proposal_id, key).receipt == receipt
    actual = counts(data)
    assert actual["student"] == 1 and actual["conversation_run"] == 1 and actual["conversation_import"] == 1
    assert actual["conversation_provenance"] == 8
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        batch = connection.execute(text("SELECT source_owner_id,restorer_id,phase FROM class_os.conversation_import")).one()
        assert batch == (world[5]["owner"], data.owner, "pending") and batch[0] != batch[1]
        assert connection.execute(text("SELECT created_by FROM class_os.student")).scalar_one() == data.owner
        assert connection.execute(text("SELECT state,version,generation FROM class_os.conversation_run")).one() == ("cancelled", 2, None)
        assert connection.execute(text("SELECT body FROM class_os.conversation_message")).scalar_one() == "合成耐久导出原文"
        assert connection.execute(text("SELECT count(*) FROM class_os.owner_account")).scalar_one() == 1
        assert not connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.business_audit WHERE actor_id=:source)"), {"source": world[5]["owner"]}).scalar_one()
        validate_role_guards(connection, profile="conversation-d1")
    ordinary_denied(data)
    # Reopened repository still cannot expose imported content or start a run.
    reopened = Database(data.dbs["runtime"].engine.url, profile="conversation-d1")
    try:
        with pytest.raises(CommandRejected):
            ConversationQueryGateway(data.identity, ConversationBusinessStore(reopened, data.restrictions),
                                     clock=lambda: data.clock[0]).context(*data.credentials)
    finally:
        reopened.close()


@pytest.mark.db
def test_denied_source_proof_is_preserved_without_poisoning_export_or_import(world, target):
    source_store = SourceTransferStore(world[2].database, world[3])
    query = SourceTransferQueryGateway(world[0].identity, source_store, clock=world[0].clock)
    with pytest.raises(CommandRejected):
        query.committed_source(*world[6], uuid4())
    data = prepare(world, target)
    rows = [r for r in data.artifact.bundle["audit_refs"] if r["action"] == "conversation.transfer.proof"]
    assert len(rows) == 1 and rows[0]["outcome"] == "denied"
    commit(data, approved(data))
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT event_id,outcome FROM class_os.conversation_source_audit WHERE action='conversation.transfer.proof'")).one() == (UUID(rows[0]["event_id"]), "denied")
    ordinary_denied(data)


@pytest.mark.db
def test_audit_failure_rolls_back_sql_but_keeps_target_fence(world, target, monkeypatch):
    data = prepare(world, target)
    prepared = approved(data)
    before = counts(data)
    original = data.store.audit
    monkeypatch.setattr(data.store, "audit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic audit failure")))
    with pytest.raises(AuditUnavailable):
        commit(data, prepared)
    assert counts(data) == before and ProtectedTargetImport(data.restrictions).present()
    monkeypatch.setattr(data.store, "audit", original)
    ordinary_denied(data)
    assert commit(data, prepared).resource_id == data.command.attempt_id


@pytest.mark.db
def test_late_verification_denial_rolls_back_instead_of_committing_partial_import(world, target, monkeypatch):
    data = prepare(world, target)
    prepared = approved(data)
    before = counts(data)
    original = TargetImportTransaction._snapshot
    monkeypatch.setattr(TargetImportTransaction, "_snapshot", lambda *a: (_ for _ in ()).throw(CommandRejected()))
    with pytest.raises(RuntimeError, match="SQL must roll back"):
        commit(data, prepared)
    assert counts(data) == before
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        assert not connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.command_receipt WHERE resource_id=:id)"), {"id": data.command.attempt_id}).scalar_one()
    ordinary_denied(data)
    monkeypatch.setattr(TargetImportTransaction, "_snapshot", original)
    assert commit(data, prepared).resource_id == data.command.attempt_id


@pytest.mark.db
def test_real_post_insert_restriction_corruption_rolls_back_all_sql(world, target, monkeypatch):
    data = prepare(world, target)
    prepared, before = approved(data), counts(data)
    path = data.restrictions.root / RESTRICTION_FILE
    original_file, original_snapshot = path.read_bytes(), TargetImportTransaction._snapshot
    def corrupt_then_verify(self, binding, now):
        path.write_bytes(b"synthetic late restriction corruption")
        return original_snapshot(self, binding, now)
    monkeypatch.setattr(TargetImportTransaction, "_snapshot", corrupt_then_verify)
    with pytest.raises(RuntimeError, match="SQL must roll back"):
        commit(data, prepared)
    assert counts(data) == before
    ordinary_denied(data)
    # Repair only this disposable fault fixture, not an application repair API.
    path.write_bytes(original_file)
    monkeypatch.setattr(TargetImportTransaction, "_snapshot", original_snapshot)
    assert commit(data, prepared).resource_id == data.command.attempt_id


@pytest.mark.db
def test_concurrent_same_import_commits_once(world, target):
    data = prepare(world, target)
    prepared, key = approved(data), uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: commit(data, prepared, key), range(2)))
    assert receipts[0] == receipts[1] and counts(data)["conversation_import"] == 1


@pytest.mark.db
@pytest.mark.parametrize("fault", ["missing", "corrupt", "directory", "wrong-root"])
def test_sql_pending_never_bypasses_lost_or_foreign_target_evidence(world, target, fault, tmp_path):
    data = prepare(world, target)
    prepared, key = approved(data), uuid4()
    commit(data, prepared, key)
    path = data.restrictions.root / FILE_NAME
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"synthetic broken target proof")
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    else:
        foreign = tmp_path / "foreign-target"
        foreign.mkdir()
        data.restrictions = ProtectedConversationRestrictions(foreign, data.credentials[3], codec=fixture_codec)
        data.store.restrictions = data.restrictions
    ordinary_denied(data)
    with pytest.raises(CommandRejected):
        commit(data, prepared, key)


@pytest.mark.db
def test_cross_thread_reused_child_ids_keep_composite_provenance(world, target):
    with world[4].transaction() as connection:
        values = {**world[5], "thread": uuid4()}
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
        message(connection, values)
        original = connection.execute(text("SELECT message_id FROM class_os.conversation_message WHERE thread_id=:id"), {"id": world[5]["thread"]}).scalar_one()
        connection.execute(text("UPDATE class_os.conversation_message SET message_id=:message WHERE thread_id=:thread"),
                           {"message": original, "thread": values["thread"]})
    data = prepare(world, target)
    commit(data, approved(data))
    assert counts(data)["conversation_provenance"] == 12
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(DISTINCT thread_id) FROM class_os.conversation_provenance WHERE entity_kind='conversation_run'")).scalar_one() == 2


@pytest.mark.db
def test_multiple_clear_markers_survive_rollback_and_same_attempt_retry(world, target, monkeypatch):
    with world[4].transaction() as connection:
        values = {**world[5], "thread": uuid4(), "turn": uuid4(), "run": uuid4(), "key": uuid4()}
        thread(connection, values)
        turn(connection, values)
        queued(connection, values)
        message(connection, values)
    control_commit(world, ClearConversation(world[5]["thread"], world[5]["class"], world[5]["term"], 1))
    control_commit(world, ClearConversation(values["thread"], values["class"], values["term"], 1))
    data = prepare(world, target, terminal=False)
    prepared, before = approved(data), counts(data)
    original = data.store.audit
    monkeypatch.setattr(data.store, "audit", lambda *a: (_ for _ in ()).throw(RuntimeError("synthetic rollback")))
    with pytest.raises(AuditUnavailable):
        commit(data, prepared)
    assert counts(data) == before and len(data.restrictions.read().markers) == 2
    monkeypatch.setattr(data.store, "audit", original)
    commit(data, prepared)
    with data.dbs["migrator"].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT bool_and(body IS NULL AND visibility='restricted') FROM class_os.conversation_message")).scalar_one()
        assert connection.execute(text("SELECT epoch FROM class_os.conversation_control")).scalar_one() == 2
    ordinary_denied(data)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["hash", "source-file", "source-receipt", "target-nonempty", "old-auth"])
def test_invalid_stage_refuses_before_target_fence(world, target, fault):
    data = prepare(world, target)
    if fault == "hash":
        data.command = replace(data.command, package_hash="0" * 64)
    elif fault == "source-file":
        from class_os.infrastructure.source_transfer import FILE_NAME as SOURCE_FILE
        (world[3].root / SOURCE_FILE).write_bytes(b"synthetic corrupt source")
    elif fault == "source-receipt":
        with world[4].transaction() as connection:
            connection.execute(text("DELETE FROM class_os.command_receipt WHERE resource_id=:attempt"), {"attempt": data.command.attempt_id})
    elif fault == "target-nonempty":
        gateway = ConversationBusinessGateway(data.identity, ConversationBusinessStore(data.dbs["runtime"], data.restrictions), clock=lambda: data.clock[0])
        proposal = gateway.preview(*data.credentials, class_command())
        nonce = gateway.approve(*data.credentials, proposal.proposal_id, proposal.payload_hash)
        gateway.commit(*data.credentials, proposal.proposal_id, uuid4(), nonce)
    else:
        data.clock[0] += timedelta(minutes=6)
    before = counts(data)
    with pytest.raises((CommandRejected, IdentityDenied)):
        data.gateway.preview(*data.credentials, data.command)
    assert counts(data) == before and not ProtectedTargetImport(data.restrictions).present()


@pytest.mark.db
def test_file_only_pending_rejects_old_business_approval_and_foreign_root(world, target, monkeypatch, tmp_path):
    data = prepare(world, target)
    native = ConversationBusinessGateway(data.identity, ConversationBusinessStore(data.dbs["runtime"], data.restrictions), clock=lambda: data.clock[0])
    old = native.preview(*data.credentials, class_command())
    nonce = native.approve(*data.credentials, old.proposal_id, old.payload_hash)
    prepared = approved(data)
    original = data.store.audit
    monkeypatch.setattr(data.store, "audit", lambda *a: (_ for _ in ()).throw(RuntimeError("synthetic rollback")))
    with pytest.raises(AuditUnavailable):
        commit(data, prepared)
    monkeypatch.setattr(data.store, "audit", original)
    with pytest.raises(CommandRejected):
        native.commit(*data.credentials, old.proposal_id, uuid4(), nonce)
    wrong_root = tmp_path / "fresh-wrong-root"
    wrong_root.mkdir()
    wrong = ConversationBusinessGateway(data.identity, ConversationBusinessStore(data.dbs["runtime"],
        ProtectedConversationRestrictions(wrong_root, data.credentials[3], codec=fixture_codec)), clock=lambda: data.clock[0])
    with pytest.raises(CommandRejected):
        wrong.commit(*data.credentials, old.proposal_id, uuid4(), nonce)
    assert counts(data)["academic_term"] == 0


@pytest.mark.db
def test_pending_checkpoint_covers_new_stores_and_refuses_provenance_tamper(world, target):
    data = prepare(world, target)
    commit(data, approved(data))
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
    backup = SyntheticBackup(Runtime(), codec=fixture_codec, profile="conversation-d1")
    artifact = backup.create()
    result = backup.check(artifact)
    assert result["table_count"] == 30 and result["activation_allowed"] is False
    with data.dbs["migrator"].transaction() as connection:
        connection.execute(text("UPDATE class_os.conversation_provenance SET source_hash=:hash WHERE entity_kind='student'"), {"hash": "0" * 64})
    from class_os.infrastructure.operator_backup import BackupRejected
    with pytest.raises(BackupRejected):
        backup.create()
    # Original owned artifact still restores/verifies independently, never activates.
    assert backup.check(artifact)["activation_allowed"] is False


@pytest.mark.db
@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI and PostgreSQL composition")
@pytest.mark.parametrize("target", [True], indirect=True)
def test_actual_dpapi_and_pg_target_import(world, target):
    data = prepare(world, target)
    commit(data, approved(data))
    assert counts(data)["conversation_import"] == 1
    assert data.command.package_hash.encode() not in (data.restrictions.root / FILE_NAME).read_bytes()
    ordinary_denied(data)


@pytest.mark.db
def test_expanded_provenance_limit_refuses_before_publishing_target_fence(world, target):
    with world[4].transaction() as connection:
        connection.execute(text("""INSERT INTO class_os.student
            (workspace_id,student_id,name,status,version,created_by,updated_by,created_at,updated_at)
            VALUES(:workspace,:student,'合成容量学生','inactive',1,:owner,:owner,:at,:at)"""),
            [{"workspace": world[5]["workspace"], "student": uuid4(), "owner": world[5]["owner"], "at": world[5]["at"]}
             for _ in range(1800)])
    data = prepare(world, target)
    assert len(data.store.candidate.encoded) < 1048576
    with pytest.raises(CommandRejected):
        data.gateway.preview(*data.credentials, data.command)
    assert not ProtectedTargetImport(data.restrictions).present() and counts(data)["student"] == 0


@pytest.mark.db
def test_actual_pg_row_budget_refuses_canonical_boundary_without_writes(database_urls):
    from copy import deepcopy
    import rfc8785
    from test_target_import import pending
    from class_os.domain.conversation_exit_v4 import snapshot_hash, validate_v4
    from class_os.domain.exit_package import checksum
    from class_os.infrastructure.target_import_store import validate_projection_budget
    value = pending()
    batch = value["recovery"]["conversation_import"][0]
    base = deepcopy(value["core"]["student"][0])
    students, origins = [], []
    for _ in range(2000):
        row = {**base, "student_id": str(uuid4()), "status": "inactive"}
        original = {**row, "workspace_id": batch["source_workspace_id"],
                    "created_by": batch["source_owner_id"], "updated_by": batch["source_owner_id"]}
        students.append(row)
        origins.append({"workspace_id": batch["workspace_id"], "attempt_id": batch["attempt_id"],
            "entity_kind": "student", "thread_id": None, "resource_id": row["student_id"],
            "source_version": row["version"], "source_hash": checksum(original)})
    initial_students = deepcopy(value["core"]["student"])
    initial_origins = deepcopy(value["recovery"]["conversation_provenance"])
    def fill(count):
        value["core"]["student"] = initial_students + students[:count]
        value["recovery"]["conversation_provenance"] = initial_origins + origins[:count]
        value["snapshot_hash"] = snapshot_hash(value["core"], value["conversations"], value["restriction_evidence"], value["recovery"])
        value["package_checksum"] = checksum({k: v for k, v in value.items() if k != "package_checksum"})
        return len(rfc8785.dumps(value))
    low, high = 0, 2000
    assert fill(high) > 1048576
    while low + 1 < high:
        middle = (low + high) // 2
        if fill(middle) <= 1048576:
            low = middle
        else:
            high = middle
    assert fill(low) <= 1048576 and validate_v4(value)
    database = Database(database_urls["migrator"], migration=True)
    try:
        with database.transaction(read_only=True) as connection:
            with pytest.raises(CommandRejected):
                validate_projection_budget(connection, (value["core"], value["conversations"], value["restriction_evidence"], value["recovery"]))
            assert connection.execute(text("SELECT to_regclass('class_os.conversation_import')")).scalar_one() is None
    finally:
        database.close()
