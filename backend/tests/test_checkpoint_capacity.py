"""Bounded owned D4 snapshots, not portable exit or encryption evidence."""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import text

from class_os.infrastructure.operator_backup import SyntheticBackup, BackupRejected, encoded
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
    assert packet['kind'] == 'classmatter.owned-classroom-work-backup.v2'
    assert packet['inventory'] == before
    checked = checkpoint.check_current_restrictions(artifact, store.restrictions)
    assert checked['snapshot_integrity_verified'] and not checked['activation_allowed']
    with owner.transaction(read_only=True) as connection:
        assert checkpoint._inventory(connection, profile='classroom-work-d4') == before


@pytest.mark.db
def test_prior_kind_remains_readable_and_keeps_its_original_row_cap(checkpoint, classroom_work):
    artifact = checkpoint.create()
    packet, _ = checkpoint._open(artifact)
    prior = {**packet, 'kind':'classmatter.owned-classroom-work-backup.v1', 'id':str(uuid4())}
    from uuid import UUID
    checkpoint._publish(UUID(prior['id']), fixture_codec(encoded(prior)))
    assert checkpoint.check(UUID(prior['id']))['snapshot_integrity_verified']
    for kind, rows in [('classmatter.owned-classroom-work-backup.v1',10001),
                       ('classmatter.owned-classroom-work-backup.v2',50001),
                       ('classmatter.owned-classroom-work-backup.v3',1)]:
        changed = {**packet, 'kind':kind, 'id':str(uuid4()),
            'inventory':{name:dict(value) for name,value in packet['inventory'].items()}}
        changed['inventory']['identity_audit']['rows'] = rows
        checkpoint._publish(UUID(changed['id']), fixture_codec(encoded(changed)))
        with pytest.raises(BackupRejected):
            checkpoint._open(UUID(changed['id']))


@pytest.mark.parametrize('profile,rows,size', [('classroom-work-d4',1,12 * 1024 * 1024 + 1),
    ('classroom-work-d4',50001,1), ('r1',10001,1), ('workspace-chat-d3',10001,1)])
def test_capacity_still_rejects_large_data_before_aggregation(profile, rows, size):
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
        SyntheticBackup._inventory(Connection(), profile=profile)
