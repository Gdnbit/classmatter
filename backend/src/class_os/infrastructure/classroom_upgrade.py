"""Explicit checkpointed D3→D4 operator; never runs at application startup."""
import os
from uuid import uuid4
from sqlalchemy import text
from .local_runtime import LocalRuntime
from .operator_backup import SyntheticBackup, encoded
from .persistence.database import Database, migrate
from .persistence.schema_inventory import schema_profile
from .workspace_local_runtime import surface
from .workbench_upgrade import (UpgradeRejected, descriptor, load_plan, save_plan, digest, business_digest,
    known_service_stopped, native_anchor, no_clients, read_bytes, publish_manifest)

JOURNAL = 'classroom-work-upgrade.dpapi'
KIND = 'classmatter.owned-classroom-work-upgrade.v1'


def described(runtime):
    return descriptor(runtime, source_profile='workspace-chat-d3', target_profile='classroom-work-d4')


def verify_upgrade_receipt(runtime):
    current, (source, target) = described(runtime)
    plan = load_plan(runtime, source, target, journal=JOURNAL, kind=KIND)
    if current.profile != 'classroom-work-d4' or plan is None:
        raise UpgradeRejected()
    return plan


def upgrade_classroom(runtime):
    if os.name != 'nt' or type(runtime) is not LocalRuntime or runtime.profile not in ('workspace-chat-d3', 'classroom-work-d4'):
        raise UpgradeRejected()
    current, (source, target) = described(runtime)
    plan = load_plan(current, source, target, journal=JOURNAL, kind=KIND)
    known_service_stopped(current)
    database, target_database = current.database('migrator'), None
    try:
        with database.engine.connect() as connection:
            for key in (607103029, 607103028, 607103027, 607103018, 607103017):
                if not connection.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}).scalar_one():
                    raise UpgradeRejected()
            connection.commit()
            with connection.begin():
                head = connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one()
                row, restrictions = native_anchor(connection, current)
                no_clients(connection)
                if head == '0029':
                    if plan is None or plan['owner_id'] != str(row['owner_id']) or plan['workspace_id'] != str(row['workspace_id']):
                        raise UpgradeRejected()
                    if current.profile == 'workspace-chat-d3':
                        if business_digest(SyntheticBackup._inventory(connection, profile='workspace-chat-d3')) != plan['business']:
                            raise UpgradeRejected()
                        if connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.class_exam) OR EXISTS(SELECT 1 FROM class_os.exam_result_revision)
                            OR EXISTS(SELECT 1 FROM class_os.class_seating) OR EXISTS(SELECT 1 FROM class_os.seat_revision)''')).scalar_one():
                            raise UpgradeRejected()
            if head == '0029':
                # Explicit operator-only upgrade. Retain and restore-check the
                # old schema before adding the nullable comparison column.
                backup = SyntheticBackup(current, profile='classroom-work-d4', legacy_classroom=True)
                artifact = backup.create()
                backup.check_current_restrictions(artifact, restrictions)
                packet, _ = backup._open(artifact)
                comparison_journal = 'chat-change-preview-upgrade.dpapi'
                prior = load_plan(current, source, target, journal=comparison_journal, kind='classmatter.chat-change-preview-upgrade.v1')
                save_plan(current, {'kind': 'classmatter.chat-change-preview-upgrade.v1', 'root': digest(str(current.root).encode('utf-8')),
                    'source': digest(source), 'target': digest(target), 'attempt_id': str(uuid4()), 'backup_id': str(artifact),
                    'business': business_digest(packet['inventory']), 'owner_id': str(row['owner_id']), 'workspace_id': str(row['workspace_id'])},
                    prior, journal=comparison_journal)
                with connection.begin():
                    no_clients(connection); native_anchor(connection, current)
                    if SyntheticBackup._inventory(connection, profile='classroom-work-d4') != packet['inventory']:
                        raise UpgradeRejected()
                    target_database = Database(database.engine.url, migration=True, profile='classroom-work-d4')
                    migrate(target_database, connection=connection)
                    surface(connection, profile='classroom-work-d4')
                    if connection.execute(text('SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_turn WHERE change_preview IS NOT NULL)')).scalar_one():
                        raise UpgradeRejected()
                    after = SyntheticBackup._inventory(connection, profile='classroom-work-d4')
                    if after.get('personal_summary_attempt', {}).get('rows') != 0:
                        raise UpgradeRejected()
                    after.pop('personal_summary_attempt', None)
                    turns = connection.execute(text("SELECT coalesce(jsonb_agg(to_jsonb(t)-'change_preview' ORDER BY (to_jsonb(t)-'change_preview')::text),'[]'::jsonb) FROM class_os.workspace_chat_turn t")).scalar_one()
                    after['workspace_chat_turn']['sha256'] = digest(encoded(turns))
                    after['alembic_version'] = packet['inventory']['alembic_version']
                    if after != packet['inventory']:
                        raise UpgradeRejected()
                if current.profile == 'classroom-work-d4':
                    return current
                head = schema_profile('classroom-work-d4')[0]
            if head == '0030':
                # Same columns/ACLs, wider *closed* candidate list. Verify a
                # full prior-revision restore before altering the constraint.
                if plan is None or plan['owner_id'] != str(row['owner_id']) or plan['workspace_id'] != str(row['workspace_id']):
                    raise UpgradeRejected()
                backup = SyntheticBackup(current, profile='classroom-work-d4', checkpoint_revision='0030')
                artifact = backup.create()
                backup.check_current_restrictions(artifact, restrictions)
                packet, _ = backup._open(artifact)
                activity_journal = 'chat-activity-upgrade.dpapi'
                prior = load_plan(current, source, target, journal=activity_journal, kind='classmatter.chat-activity-upgrade.v1')
                save_plan(current, {'kind': 'classmatter.chat-activity-upgrade.v1', 'root': digest(str(current.root).encode('utf-8')),
                    'source': digest(source), 'target': digest(target), 'attempt_id': str(uuid4()), 'backup_id': str(artifact),
                    'business': business_digest(packet['inventory']), 'owner_id': str(row['owner_id']), 'workspace_id': str(row['workspace_id'])},
                    prior, journal=activity_journal)
                with connection.begin():
                    no_clients(connection); native_anchor(connection, current)
                    if SyntheticBackup._inventory(connection, profile='classroom-work-d4') != packet['inventory']:
                        raise UpgradeRejected()
                    target_database = Database(database.engine.url, migration=True, profile='classroom-work-d4')
                    migrate(target_database, connection=connection)
                    surface(connection, profile='classroom-work-d4')
                    after = SyntheticBackup._inventory(connection, profile='classroom-work-d4')
                    if after.get('personal_summary_attempt', {}).get('rows') != 0:
                        raise UpgradeRejected()
                    after.pop('personal_summary_attempt', None)
                    after['alembic_version'] = packet['inventory']['alembic_version']
                    if after != packet['inventory']:
                        raise UpgradeRejected()
                head = schema_profile('classroom-work-d4')[0]
            if head == '0031':
                if plan is None or plan['owner_id'] != str(row['owner_id']) or plan['workspace_id'] != str(row['workspace_id']):
                    raise UpgradeRejected()
                backup = SyntheticBackup(current, profile='classroom-work-d4', checkpoint_revision='0031')
                artifact = backup.create()
                backup.check_current_restrictions(artifact, restrictions)
                packet, _ = backup._open(artifact)
                summary_journal = 'personal-summary-upgrade.dpapi'
                prior = load_plan(current, source, target, journal=summary_journal, kind='classmatter.personal-summary-upgrade.v1')
                save_plan(current, {'kind': 'classmatter.personal-summary-upgrade.v1', 'root': digest(str(current.root).encode('utf-8')),
                    'source': digest(source), 'target': digest(target), 'attempt_id': str(uuid4()), 'backup_id': str(artifact),
                    'business': business_digest(packet['inventory']), 'owner_id': str(row['owner_id']), 'workspace_id': str(row['workspace_id'])},
                    prior, journal=summary_journal)
                with connection.begin():
                    no_clients(connection); native_anchor(connection, current)
                    if SyntheticBackup._inventory(connection, profile='classroom-work-d4') != packet['inventory']:
                        raise UpgradeRejected()
                    target_database = Database(database.engine.url, migration=True, profile='classroom-work-d4')
                    migrate(target_database, connection=connection)
                    surface(connection, profile='classroom-work-d4')
                    after = SyntheticBackup._inventory(connection, profile='classroom-work-d4')
                    if after.pop('personal_summary_attempt')['rows'] != 0:
                        raise UpgradeRejected()
                    after['alembic_version'] = packet['inventory']['alembic_version']
                    if after != packet['inventory']:
                        raise UpgradeRejected()
                head = schema_profile('classroom-work-d4')[0]
            with connection.begin():
                if head == schema_profile('classroom-work-d4')[0]:
                    surface(connection, profile='classroom-work-d4')
                    if plan is None or plan['owner_id'] != str(row['owner_id']) or plan['workspace_id'] != str(row['workspace_id']):
                        raise UpgradeRejected()
                    if current.profile == 'classroom-work-d4':
                        return current
                    if business_digest(SyntheticBackup._inventory(connection, profile='workspace-chat-d3')) != plan['business']:
                        raise UpgradeRejected()
                    if connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.class_exam) OR EXISTS(SELECT 1 FROM class_os.exam_result_revision)
                        OR EXISTS(SELECT 1 FROM class_os.class_seating) OR EXISTS(SELECT 1 FROM class_os.seat_revision)''')).scalar_one():
                        raise UpgradeRejected()
                elif head != '0028' or current.profile != 'workspace-chat-d3':
                    raise UpgradeRejected()
            if head == '0028':
                with connection.begin():
                    surface(connection)
                backup = SyntheticBackup(current, profile='workspace-chat-d3')
                artifact = backup.create()
                backup.check_current_restrictions(artifact, restrictions)
                packet, _ = backup._open(artifact)
                prepared = {'kind': KIND, 'root': digest(str(current.root).encode('utf-8')), 'source': digest(source), 'target': digest(target),
                    'attempt_id': str(uuid4()), 'backup_id': str(artifact), 'business': business_digest(packet['inventory']),
                    'owner_id': str(row['owner_id']), 'workspace_id': str(row['workspace_id'])}
                save_plan(current, prepared, plan, journal=JOURNAL); plan = prepared
                target_database = Database(database.engine.url, migration=True, profile='classroom-work-d4')
                with connection.begin():
                    no_clients(connection); native_anchor(connection, current); surface(connection)
                    if SyntheticBackup._inventory(connection, profile='workspace-chat-d3') != packet['inventory']:
                        raise UpgradeRejected()
                    migrate(target_database, connection=connection)
                    surface(connection, profile='classroom-work-d4')
                    if business_digest(SyntheticBackup._inventory(connection, profile='workspace-chat-d3')) != plan['business']:
                        raise UpgradeRejected()
            if read_bytes(current.manifest, 16384) != source:
                raise UpgradeRejected()
            publish_manifest(current, target)
            return LocalRuntime(current.root, profile='classroom-work-d4')
    except Exception:
        raise UpgradeRejected() from None
    finally:
        if target_database is not None:
            target_database.close()
        database.close()
