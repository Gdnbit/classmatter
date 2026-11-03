"""Disposable PostgreSQL D2 documents through original identity/BCG transactions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
import psycopg
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from class_os.application.audit import AuditUnavailable
from class_os.application.documents import DocumentBusinessGateway, DocumentQueryGateway
from class_os.application.roster import CommandRejected
from class_os.domain.conversation_control import InitializeConversationControl
from class_os.domain.documents import CreateDocument, ReviseDocument, ChangeDocumentState
from class_os.infrastructure.documents import DocumentStore
from class_os.infrastructure.persistence.database import Database, migrate
from class_os.infrastructure.persistence.schema_inventory import validate_surface, schema_profile
from class_os.infrastructure.persistence.role_guards import validate_role_guards
from class_os.infrastructure.operator_backup import SyntheticBackup, BackupRejected
from class_os.infrastructure.documents import validate_document_integrity
from test_conversation_control import control, commit, storage, roster, identity
from test_model_secrets import fixture_codec


@pytest.fixture
def documents(control, database_urls):
    commit(control, InitializeConversationControl(uuid4()))
    owner = Database(database_urls['migrator'], migration=True, profile='workbench-d2')
    runtime = Database(database_urls['runtime'], profile='workbench-d2')
    migrate(owner)
    store = DocumentStore(runtime, control[3])
    gateway = DocumentBusinessGateway(control[0].identity, store, clock=lambda: control[7][0])
    query = DocumentQueryGateway(control[0].identity, store, clock=lambda: control[7][0])
    try:
        yield gateway, query, store, owner, runtime, control
    finally:
        runtime.close()
        owner.close()


def create(data):
    values = data[5][5]
    return CreateDocument(uuid4(), values['class'], values['term'], '合成班级小结', '第一行\r\n第二行', 'markdown')


def saved(data, command, key=None):
    gateway, _, _, _, _, control = data
    credentials = control[6]
    proposal = gateway.preview(*credentials, command)
    approval = gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
    return gateway.commit(*credentials, proposal.proposal_id, key or uuid4(), approval)


def read(data, command, **options):
    return data[1].document(*data[5][6], command.class_id, command.term_id, command.document_id, **options)


@pytest.mark.db
def test_d2_explicit_upgrade_preserves_old_rows_and_cannot_start_legacy_store(documents):
    _, _, _, owner, _, control = documents
    migrate(owner)
    with owner.transaction(read_only=True) as connection:
        assert validate_surface(connection, complete=True, profile='workbench-d2') == schema_profile('workbench-d2')[1]
        validate_role_guards(connection, profile='workbench-d2')
        assert connection.execute(text('SELECT count(*) FROM class_os.student')).scalar_one() == 1
        assert connection.execute(text('SELECT count(*) FROM class_os.conversation_control')).scalar_one() == 1
    with pytest.raises(RuntimeError, match='Unregistered'):
        migrate(control[4])
    # A legacy store cannot silently export only the old tables after upgrade.
    with pytest.raises(RuntimeError, match='schema'):
        with control[2].atomic():
            pass
    with pytest.raises(ValueError, match='profile'):
        DocumentStore(control[2].database, control[3])


@pytest.mark.db
def test_document_preview_approval_commit_receipt_and_reopen(documents):
    gateway, query, _, _, runtime, control = documents
    command = create(documents)
    proposal = gateway.preview(*control[6], command)
    assert proposal.risk == 'W2'
    assert query.documents(*control[6], command.class_id, command.term_id) == ()
    key = uuid4()
    with pytest.raises(CommandRejected):
        gateway.commit(*control[6], proposal.proposal_id, key)
    approval = gateway.approve(*control[6], proposal.proposal_id, proposal.payload_hash)
    receipt = gateway.commit(*control[6], proposal.proposal_id, key, approval)
    assert gateway.commit(*control[6], proposal.proposal_id, key, approval) == receipt
    assert query.command_status(*control[6], proposal.proposal_id, key).receipt == receipt
    reopened = DocumentQueryGateway(gateway.identity, DocumentStore(runtime, control[3]), clock=gateway.clock)
    row = reopened.document(*control[6], command.class_id, command.term_id, command.document_id)
    assert row['body'] == command.body and row['version'] == 1
    assert query.documents(*control[6], command.class_id, command.term_id)[0]['document_id'] == command.document_id
    with documents[3].transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.working_document_revision')).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='document.read'")).scalar_one() == 1


@pytest.mark.db
def test_revision_archive_restore_history_and_old_preview_conflict(documents):
    command = create(documents)
    saved(documents, command)
    revise = ReviseDocument(command.document_id, command.class_id, command.term_id, 1, '合成更新', '<script>literal text</script>')
    stale = documents[0].preview(*documents[5][6], revise)
    saved(documents, revise)
    with pytest.raises(CommandRejected):
        documents[0].approve(*documents[5][6], stale.proposal_id, stale.payload_hash)
    for operation, previous in (('document.archive', 2), ('document.restore', 3)):
        saved(documents, ChangeDocumentState(operation, command.document_id, command.class_id, command.term_id, previous))
        if previous == 2:
            with pytest.raises(CommandRejected):
                saved(documents, replace(revise, expected_version=3))
    history = read(documents, command, history=True)
    assert [row['version'] for row in history] == [4, 3, 2, 1]
    assert [row['status'] for row in history] == ['draft', 'archived', 'draft', 'draft']
    assert history[0]['body'] == history[1]['body'] == history[2]['body'] == revise.body
    assert history[3]['body'] == command.body


@pytest.mark.db
def test_class_scope_identity_and_archived_class_are_enforced(documents):
    command = create(documents)
    saved(documents, command)
    for field in ('class_id', 'term_id', 'document_id'):
        with pytest.raises(CommandRejected):
            read(documents, replace(command, **{field: uuid4()}))
    with pytest.raises(CommandRejected):
        documents[0].preview(*documents[5][6], replace(command, class_id=uuid4(), document_id=uuid4()))
    with documents[3].transaction() as connection:
        connection.execute(text("UPDATE class_os.school_class SET status='archived'"))
    with pytest.raises(CommandRejected):
        saved(documents, ReviseDocument(command.document_id, command.class_id, command.term_id, 1, '合成更新', '内容'))
    assert read(documents, command)['version'] == 1  # Read history remains available.


@pytest.mark.db
def test_audit_failure_rolls_back_document_and_receipt(documents, monkeypatch):
    command = create(documents)
    gateway, _, store, owner, _, control = documents
    proposal = gateway.preview(*control[6], command)
    approval = gateway.approve(*control[6], proposal.proposal_id, proposal.payload_hash)
    monkeypatch.setattr(store, 'audit', lambda *args: None)
    with pytest.raises(AuditUnavailable):
        gateway.commit(*control[6], proposal.proposal_id, uuid4(), approval)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.working_document')).scalar_one() == 0
        assert connection.execute(text('SELECT count(*) FROM class_os.working_document_revision')).scalar_one() == 0
        assert connection.execute(text('SELECT state FROM class_os.command_proposal WHERE proposal_id=:p'),
                                  {'p': proposal.proposal_id}).scalar_one() == 'approved'


@pytest.mark.db
def test_compare_and_swap_race_has_one_revision(documents):
    command = create(documents)
    saved(documents, command)
    changes = [ReviseDocument(command.document_id, command.class_id, command.term_id, 1, '合成并发修改', body) for body in ('甲', '乙')]
    gateway, credentials = documents[0], documents[5][6]
    approved = []
    for change in changes:
        proposal = gateway.preview(*credentials, change)
        approved.append((proposal, gateway.approve(*credentials, proposal.proposal_id, proposal.payload_hash)))
    def attempt(item):
        try:
            return gateway.commit(*credentials, item[0].proposal_id, uuid4(), item[1]).version
        except CommandRejected:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(map(str, pool.map(attempt, approved))) == ['2', 'conflict']
    assert len(read(documents, command, history=True)) == 2


@pytest.mark.db
@pytest.mark.parametrize('statement', [
    'UPDATE class_os.working_document_revision SET body=body',
    'DELETE FROM class_os.working_document_revision',
    'UPDATE class_os.working_document SET owner_id=owner_id',
    'ALTER TABLE class_os.working_document ADD COLUMN extra text',
])
def test_runtime_role_cannot_rewrite_history_identity_or_schema(documents, statement):
    with pytest.raises(ProgrammingError):
        with documents[4].transaction() as connection:
            connection.execute(text(statement))


@pytest.mark.db
def test_expanded_permissions_are_detected_without_disabling_d1_guards(documents):
    with documents[3].transaction() as connection:
        connection.execute(text('GRANT UPDATE(body) ON class_os.working_document_revision TO class_os_runtime'))
        with pytest.raises(RuntimeError, match='role safety'):
            validate_role_guards(connection, profile='workbench-d2')
    with documents[3].transaction() as connection:
        connection.execute(text('REVOKE UPDATE(body) ON class_os.working_document_revision FROM class_os_runtime'))
        connection.execute(text('GRANT UPDATE(ordinal) ON class_os.conversation_turn TO class_os_runtime'))
        with pytest.raises(RuntimeError, match='role safety'):
            validate_role_guards(connection, profile='workbench-d2')


@pytest.mark.db
def test_original_protected_root_is_required_before_document_reads(documents, tmp_path):
    from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions
    command = create(documents)
    saved(documents, command)
    wrong = ProtectedConversationRestrictions(tmp_path / 'wrong-root', documents[5][5]['workspace'], codec=fixture_codec)
    query = DocumentQueryGateway(documents[0].identity, DocumentStore(documents[4], wrong), clock=documents[0].clock)
    with pytest.raises(CommandRejected):
        query.documents(*documents[5][6], command.class_id, command.term_id)


@pytest.mark.db
def test_d2_complete_checkpoint_restore_includes_document_revisions(documents, database_urls, postgres_cluster, request):
    command = create(documents)
    saved(documents, command)
    saved(documents, ReviseDocument(command.document_id, command.class_id, command.term_id, 1, '合成更新', '保留所有版本'))
    binaries = Path(request.config.getoption('--pg-root')).resolve()
    if (binaries / 'bin').is_dir():
        binaries /= 'bin'
    class FixtureRuntime:
        root = documents[5][3].root
        def configuration(self):
            return {'profile': 'classmatter-owned-synthetic-workbench-d2', 'pg_bin': str(binaries),
                    'port': postgres_cluster['port'], 'database': database_urls['migrator'].database}
        def password(self, role):
            assert role == 'migrator'
            return ''  # Disposable trust-auth fixture; not a developer credential.
        def database(self, role):
            assert role == 'migrator'
            return Database(database_urls[role], migration=True, profile='workbench-d2')
        @contextmanager
        def admin(self):
            with psycopg.connect(**postgres_cluster, autocommit=True) as connection:
                yield connection
    backup = SyntheticBackup(FixtureRuntime(), codec=fixture_codec, profile='workbench-d2')
    artifact = backup.create()
    packet, _ = backup._open(artifact)
    assert packet['inventory']['working_document']['rows'] == 1
    assert packet['inventory']['working_document_revision']['rows'] == 2
    result = backup.check_current_restrictions(artifact, documents[5][3])
    assert result['schema_version'] == 'classmatter.workbench-backup-check.v1'
    assert result['snapshot_integrity_verified'] and result['temporary_clone_removed']
    assert result['activation_allowed'] is False and result['complete_exit'] is False
    assert read(documents, command)['body'] == '保留所有版本'
    # Existing D1 backup cannot omit D2 and report a successful backup.
    with pytest.raises(BackupRejected):
        SyntheticBackup(FixtureRuntime(), codec=fixture_codec, profile='conversation-d1').create()


@pytest.mark.db
def test_checkpoint_rejects_inconsistent_revision_chain(documents):
    command = create(documents)
    saved(documents, command)
    saved(documents, ChangeDocumentState('document.archive', command.document_id, command.class_id, command.term_id, 1))
    with documents[3].transaction() as connection:
        validate_document_integrity(connection)
        # Trusted migrator corruption drill; runtime lacks this privilege.
        connection.execute(text("UPDATE class_os.working_document_revision SET body='changed' WHERE version=2"))
        with pytest.raises(ValueError, match='revision chain'):
            validate_document_integrity(connection)
