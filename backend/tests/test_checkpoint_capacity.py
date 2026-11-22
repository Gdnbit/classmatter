"""Bounded owned D4 snapshots, not portable exit or encryption evidence."""
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import text

from class_os.infrastructure.operator_backup import (
    D4_KIND_V1, D4_KIND_V2, D4_KIND_V3, MIB, BackupRejected, SyntheticBackup, encoded,
)
from class_os.infrastructure.persistence.database import Database
from test_model_secrets import fixture_codec
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


@pytest.fixture
def checkpoint(classroom_work, postgres_cluster, request):
    owner, store = classroom_work[3], classroom_work[5]
    binaries = Path(request.config.getoption('--pg-root')).resolve()
    if (binaries/'bin').is_dir():
        binaries /= 'bin'
    class FixtureRuntime:
        root = store.restrictions.root
        def configuration(self):
            return {'profile':'owned-d4-fixture','pg_bin':str(binaries),
                'port':postgres_cluster['port'],'database':owner.engine.url.database}
        def password(self, role):
            assert role == 'migrator'
            return ''  # Disposable trust-auth cluster only.
        def database(self, role):
            assert role == 'migrator'
            return Database(owner.engine.url, migration=True, profile='classroom-work-d4')
        @contextmanager
        def admin(self):
            with psycopg.connect(**postgres_cluster, autocommit=True) as connection:
                yield connection
    return SyntheticBackup(FixtureRuntime(), codec=fixture_codec, profile='classroom-work-d4')


def grow_identity(owner):
    with owner.transaction() as connection:
        connection.execute(text('''INSERT INTO class_os.identity_audit(event_id,action,outcome,occurred_at)
            SELECT gen_random_uuid(),'session','allowed',TIMESTAMPTZ '2026-10-08 12:00:00+00'
            FROM generate_series(1,12000)'''))


@pytest.mark.db
def test_complete_checkpoint_preserves_identity_audit_over_ten_thousand_rows(classroom_work, checkpoint):
    owner, store = classroom_work[3], classroom_work[5]
    grow_identity(owner)
    with owner.transaction(read_only=True) as connection:
        before = checkpoint._inventory(connection, profile='classroom-work-d4')
    assert before['identity_audit']['rows'] > 10000
    artifact = checkpoint.create()
    packet, _ = checkpoint._open(artifact)
    assert packet['kind'] == D4_KIND_V3
    assert packet['inventory'] == before
    checked = checkpoint.check_current_restrictions(artifact, store.restrictions)
    assert checked['snapshot_integrity_verified'] and not checked['activation_allowed']
    with owner.transaction(read_only=True) as connection:
        assert checkpoint._inventory(connection, profile='classroom-work-d4') == before


@pytest.mark.db
def test_prior_kinds_remain_readable_and_keep_their_original_row_caps(checkpoint):
    artifact = checkpoint.create()
    packet, _ = checkpoint._open(artifact)
    for kind in (D4_KIND_V1, D4_KIND_V2):
        prior = {**packet, 'kind': kind, 'id': str(uuid4())}
        checkpoint._publish(UUID(prior['id']), fixture_codec(encoded(prior)))
        assert checkpoint.check(UUID(prior['id']))['snapshot_integrity_verified']
    for kind, rows in [(D4_KIND_V1, 10_001), (D4_KIND_V2, 50_001), (D4_KIND_V3, 50_001),
                       ('classmatter.owned-classroom-work-backup.v99', 1)]:
        changed = {**packet, 'kind':kind, 'id':str(uuid4()),
            'inventory':{name:dict(value) for name,value in packet['inventory'].items()}}
        changed['inventory']['identity_audit']['rows'] = rows
        checkpoint._publish(UUID(changed['id']), fixture_codec(encoded(changed)))
        with pytest.raises(BackupRejected):
            checkpoint._open(UUID(changed['id']))


def grow_documents(classroom_work, count):
    _, _, _, owner, _, store, _, class_id, term_id, _ = classroom_work
    with owner.transaction() as connection:
        # Compressible synthetic documents cross the logical limit independently
        # of the physical archive size. They retain complete revision chains.
        connection.execute(text("""WITH docs AS (
            INSERT INTO class_os.working_document
                (workspace_id,document_id,owner_id,class_id,term_id,status,version,created_at,updated_at)
            SELECT workspace_id,gen_random_uuid(),owner_id,:class_id,:term_id,'draft',1,now(),now()
            FROM class_os.owner_account CROSS JOIN generate_series(1,:count)
            RETURNING workspace_id,document_id,owner_id,created_at)
            INSERT INTO class_os.working_document_revision
                (workspace_id,document_id,version,status,title,body,format,operation,created_by,created_at)
            SELECT workspace_id,document_id,1,'draft','Synthetic capacity fixture',
                repeat('课堂材料', 21000),'plain-text','document.create',owner_id,created_at FROM docs
            """), {"class_id": class_id, "term_id": term_id, "count": count})
    return owner, store


@pytest.mark.db
def test_grown_document_history_restores_without_weakening_v2(checkpoint, classroom_work):
    owner, store = grow_documents(classroom_work, 52)
    with owner.transaction(read_only=True) as connection:
        before = checkpoint._inventory(connection, profile='classroom-work-d4')
        assert before['working_document_revision']['rows'] == 52
        with pytest.raises(BackupRejected):
            checkpoint._inventory(connection, profile='classroom-work-d4', kind=D4_KIND_V2)
    artifact = checkpoint.create()
    packet, _ = checkpoint._open(artifact)
    assert packet['kind'] == D4_KIND_V3 and packet['inventory'] == before
    checked = checkpoint.check_current_restrictions(artifact, store.restrictions)
    assert checked['snapshot_integrity_verified'] and checked['source_preserved']
    legacy_id = uuid4()
    checkpoint._publish(legacy_id, fixture_codec(encoded({**packet, 'kind': D4_KIND_V2, 'id': str(legacy_id)})))
    with pytest.raises(BackupRejected):
        checkpoint.check(legacy_id)
    with owner.transaction(read_only=True) as connection:
        assert checkpoint._inventory(connection, profile='classroom-work-d4') == before


@pytest.mark.db
def test_oversized_documents_reject_before_body_validation_and_dump(checkpoint, classroom_work, monkeypatch):
    from class_os.infrastructure import documents

    owner, _ = grow_documents(classroom_work, 90)

    def forbidden(*args, **kwargs):
        pytest.fail('Over-budget data must be rejected before reading document bodies or dumping')

    monkeypatch.setattr(documents, 'validate_document_integrity', forbidden)
    monkeypatch.setattr(checkpoint, '_pg', forbidden)
    with pytest.raises(BackupRejected):
        checkpoint.create()
    assert not (checkpoint.runtime.root / 'backups').exists()
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.working_document_revision')).scalar_one() == 90


@pytest.mark.parametrize('profile,kind,rows,size', [
    ('classroom-work-d4', D4_KIND_V3, 1, 20 * MIB + 1),
    ('classroom-work-d4', D4_KIND_V2, 1, 12 * MIB + 1),
    ('classroom-work-d4', D4_KIND_V3, 50_001, 1),
    ('r1', None, 1, 12 * MIB + 1),
    ('r1', None, 10_001, 1),
    ('workspace-chat-d3', None, 10_001, 1),
])
def test_capacity_still_rejects_large_data_before_aggregation(profile, kind, rows, size):
    class Connection:
        def execute(self, query):
            sql = str(query)
            if 'alembic_version' in sql and 'SELECT version_num' in sql:
                class Version:
                    def scalar_one(self): return '0033'
                return Version()
            assert 'coalesce(sum(octet_length' in sql, 'Oversized content must not be aggregated'
            class Size:
                def one(self): return rows, size
            return Size()
    with pytest.raises(BackupRejected):
        SyntheticBackup._inventory(Connection(), profile=profile, kind=kind)
