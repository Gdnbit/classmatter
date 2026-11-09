"""Trusted owned-root upgrade, not an HTTP/Agent command or data admission."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from uuid import UUID, uuid4

from sqlalchemy import text

from .local_runtime import LocalRuntime, PROFILES, protect
from .operator_backup import SyntheticBackup
from .persistence.database import Database, migrate
from .persistence.role_guards import PRIVATE_IDENTITY_TABLES
from .conversation_restrictions import ProtectedConversationRestrictions, RestrictionHead


JOURNAL = 'workbench-upgrade.dpapi'
KIND = 'classmatter.owned-workbench-upgrade.v1'
LIMIT = 32768


class UpgradeRejected(Exception):
    def __init__(self):
        super().__init__('Owned workbench upgrade rejected; database, journal and backups preserved')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UpgradeRejected()
        result[key] = value
    return result


def read_bytes(path, limit=LIMIT):
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise UpgradeRejected()
    with path.open('rb') as source:
        value = source.read(limit + 1)
    if not 1 <= len(value) <= limit:
        raise UpgradeRejected()
    return value


def descriptor(runtime, *, source_profile='conversation-d1', target_profile='workbench-d2'):
    if (source_profile, target_profile) not in (('conversation-d1', 'workbench-d2'), ('workbench-d2', 'workspace-chat-d3'), ('workspace-chat-d3', 'classroom-work-d4')):
        raise UpgradeRejected()
    raw = read_bytes(runtime.manifest, 16384)
    value = json.loads(raw, object_pairs_hook=unique)
    if type(value) is not dict:
        raise UpgradeRejected()
    profiles = {PROFILES[name][0]: name for name in (source_profile, target_profile)}
    profile = profiles.get(value.get('profile'))
    if profile is None:
        raise UpgradeRejected()
    current = LocalRuntime(runtime.root, profile=profile)
    if current.configuration() != value:
        raise UpgradeRejected()
    source_marker = json.dumps(PROFILES[source_profile][0]).encode('ascii')
    target_marker = json.dumps(PROFILES[target_profile][0]).encode('ascii')
    # Patch exactly the profile value, preserving descriptor bytes/EOL/encoding.
    pattern = rb'("profile"\s*:\s*)' + re.escape(source_marker if profile == source_profile else target_marker)
    alternate, count = re.subn(pattern, lambda match: match[1] + (target_marker if profile == source_profile else source_marker), raw)
    if count != 1:
        raise UpgradeRejected()
    return current, (raw, alternate) if profile == source_profile else (alternate, raw)


def load_plan(runtime, source, target, *, journal=JOURNAL, kind=KIND):
    path = runtime.root / journal
    if not path.exists() and not path.is_symlink():
        return None
    raw = protect(read_bytes(path), decrypt=True)
    if type(raw) is not bytes or not 1 <= len(raw) <= LIMIT:
        raise UpgradeRejected()
    plan = json.loads(raw, object_pairs_hook=unique)
    fields = {'kind', 'root', 'source', 'target', 'attempt_id', 'backup_id', 'business', 'owner_id', 'workspace_id'}
    if type(plan) is not dict or set(plan) != fields or plan['kind'] != kind:
        raise UpgradeRejected()
    for field in ('root', 'source', 'target', 'business'):
        if type(plan[field]) is not str or not re.fullmatch('[a-f0-9]{64}', plan[field]):
            raise UpgradeRejected()
    for field in ('attempt_id', 'backup_id', 'owner_id', 'workspace_id'):
        if type(plan[field]) is not str or str(UUID(plan[field])) != plan[field]:
            raise UpgradeRejected()
    if (plan['root'] != digest(str(runtime.root).encode('utf-8'))
            or plan['source'] != digest(source) or plan['target'] != digest(target)):
        raise UpgradeRejected()
    return plan


def publish(path, raw):
    if path.is_symlink() or path.is_junction():
        raise UpgradeRejected()
    pending = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.workbench-upgrade-', suffix='.pending', delete=False) as output:
            pending = Path(output.name)
            output.write(raw); output.flush(); os.fsync(output.fileno())
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def publish_manifest(runtime, target):
    publish(runtime.manifest, target)


def save_plan(runtime, plan, prior, *, journal=JOURNAL):
    if prior is not None:
        directory = runtime.root / 'upgrade-history'
        if directory.is_symlink() or directory.is_junction():
            raise UpgradeRejected()
        directory.mkdir(mode=0o700, exist_ok=True)
        if sum(1 for _ in directory.iterdir()) >= 128:
            raise UpgradeRejected()
        archive = directory / (prior['attempt_id'] + '.dpapi')
        if archive.exists():
            if read_bytes(archive) != read_bytes(runtime.root / journal):
                raise UpgradeRejected()
        else:
            os.link(runtime.root / journal, archive)
    sealed = protect(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    if type(sealed) is not bytes or not 1 <= len(sealed) <= LIMIT:
        raise UpgradeRejected()
    publish(runtime.root / journal, sealed)


def business_digest(inventory):
    # Identity sessions can legitimately expire after a committed migration;
    # never reset them from a pre-upgrade checkpoint during forward recovery.
    value = {key: item for key, item in inventory.items() if key not in PRIVATE_IDENTITY_TABLES | {'alembic_version'}}
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def known_service_stopped(runtime):
    repository = Path(__file__).resolve().parents[4]
    for stage in ('runtime-d1', 'runtime-d2', 'runtime-d3', 'runtime-d4'):
        path = repository / 'apps/desktop/.build' / stage / 'runtime-source.json'
        if not path.is_file():
            continue
        value = json.loads(read_bytes(path, 16384), object_pairs_hook=unique)
        if (type(value) is not dict or type(value.get('runtimeRoot')) is not str
                or Path(value['runtimeRoot']).resolve() != runtime.root):
            continue  # Another owned fixture/root is not this upgrade target.
        port = value.get('servicePort')
        if type(port) is not int or not 1024 <= port <= 65535:
            raise UpgradeRejected()
        with socket.socket() as probe:
            probe.settimeout(.3)
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise UpgradeRejected()


def native_anchor(connection, runtime):
    from .source_transfer import ProtectedSourceTransfer
    from .source_retirement import ProtectedSourceRetirement
    from .target_import import ProtectedTargetImport
    from .recovery_admission import ProtectedTargetAdmission
    row = connection.execute(text('''SELECT o.owner_id,o.workspace_id,c.authority_id,c.epoch,c.head_hash,c.transfer_id
        FROM class_os.owner_account o JOIN class_os.conversation_control c USING(owner_id,workspace_id)''')).mappings().one()
    restrictions = ProtectedConversationRestrictions(runtime.root, row['workspace_id'])
    state = restrictions.compare(RestrictionHead(row['authority_id'], row['workspace_id'], row['epoch'], row['head_hash']))
    if (state.state != 'aligned' or row['transfer_id'] is not None
            or any(port(restrictions).present() for port in (ProtectedSourceTransfer, ProtectedSourceRetirement, ProtectedTargetImport, ProtectedTargetAdmission))
            or connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.conversation_import)
                OR EXISTS(SELECT 1 FROM class_os.conversation_admission)
                OR EXISTS(SELECT 1 FROM class_os.conversation_run WHERE state IN ('queued','running','cancel_requested'))''')).scalar_one()):
        raise UpgradeRejected()
    return row, restrictions


def no_clients(connection):
    # Non-superusers may see NULL backend_type for another role. Treat that
    # visibility limit as connected, rather than granting pg_read_all_stats.
    if connection.execute(text('''SELECT EXISTS(SELECT 1 FROM pg_stat_activity
        WHERE datname=current_database() AND pid<>pg_backend_pid()
            AND (backend_type IS NULL OR backend_type='client backend'))''')).scalar_one():
        raise UpgradeRejected()


def verify_upgrade_receipt(runtime):
    current, (source, target) = descriptor(runtime)
    plan = load_plan(runtime, source, target)
    if current.profile != 'workbench-d2' or plan is None:
        raise UpgradeRejected()
    return plan


def upgrade_workbench(runtime):
    """Explicit operator only; original app must be stopped before invocation.

    Locks span checkpoint, SQL commit and descriptor publication. No sessions,
    source restrictions, business records or backup artifacts are reset/deleted.
    """
    if os.name != 'nt' or type(runtime) is not LocalRuntime or runtime.profile not in ('conversation-d1', 'workbench-d2'):
        raise UpgradeRejected()
    database = target_database = None
    try:
        current, (source, target) = descriptor(runtime)
        plan = load_plan(current, source, target)
        known_service_stopped(current)
        database = current.database('migrator')
        with database.engine.connect() as connection:
            for key in (607103027, 607103018, 607103017):
                if not connection.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}).scalar_one():
                    raise UpgradeRejected()
            connection.commit()  # Session locks remain until this physical connection closes.
            with connection.begin():
                head = connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one()
                row, restrictions = native_anchor(connection, current)
                no_clients(connection)
                if head == '0027':
                    from .workbench_local_runtime import surface
                    surface(connection)
                    if (plan is None or plan['owner_id'] != str(row['owner_id']) or plan['workspace_id'] != str(row['workspace_id'])):
                        raise UpgradeRejected()
                    if current.profile == 'workbench-d2':
                        return current
                    if business_digest(SyntheticBackup._inventory(connection, profile='conversation-d1')) != plan['business']:
                        raise UpgradeRejected()
                elif head != '0026' or current.profile != 'conversation-d1':
                    raise UpgradeRejected()
            if head == '0026':
                from .durable_local_runtime import _surface
                with connection.begin():
                    _surface(connection)
                backup = SyntheticBackup(current, profile='conversation-d1')
                artifact = backup.create()
                backup.check_current_restrictions(artifact, restrictions)
                packet, _ = backup._open(artifact)
                prepared = {'kind': KIND, 'root': digest(str(current.root).encode('utf-8')),
                    'source': digest(source), 'target': digest(target), 'attempt_id': str(uuid4()), 'backup_id': str(artifact),
                    'business': business_digest(packet['inventory']), 'owner_id': str(row['owner_id']), 'workspace_id': str(row['workspace_id'])}
                save_plan(current, prepared, plan)
                plan = prepared
                target_database = Database(database.engine.url, migration=True, profile='workbench-d2')
                with connection.begin():
                    no_clients(connection)
                    native_anchor(connection, current)
                    _surface(connection)
                    if SyntheticBackup._inventory(connection, profile='conversation-d1') != packet['inventory']:
                        raise UpgradeRejected()
                    migrate(target_database, connection=connection)
                    from .workbench_local_runtime import surface
                    surface(connection)
                    if business_digest(SyntheticBackup._inventory(connection, profile='conversation-d1')) != plan['business']:
                        raise UpgradeRejected()
            # Crash after SQL commit is resumed by the checked 0027 branch above.
            if read_bytes(current.manifest, 16384) != source:
                raise UpgradeRejected()
            publish_manifest(current, target)
            return LocalRuntime(current.root, profile='workbench-d2')
    except Exception:
        raise UpgradeRejected() from None
    finally:
        if target_database is not None:
            target_database.close()
        if database is not None:
            database.close()
