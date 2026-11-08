"""Fixed D2→D3 owned-root operator step using the existing checkpoint protocol."""
import os
from uuid import uuid4

from sqlalchemy import text

from .local_runtime import LocalRuntime
from .operator_backup import SyntheticBackup
from .persistence.database import Database, migrate
from .workbench_upgrade import (UpgradeRejected, descriptor, load_plan, save_plan, digest, business_digest,
    known_service_stopped, native_anchor, no_clients, read_bytes, publish_manifest, upgrade_workbench)

JOURNAL = "workspace-chat-upgrade.dpapi"
KIND = "classmatter.owned-workspace-chat-upgrade.v1"


def prepare_workspace_chat(runtime, pg_root):
    """Explicit fresh developer setup, never called by desktop/API startup.

    Uses the original D1 initialization and private development identity, then
    the same checkpointed upgrade. Refuses every existing directory; failure
    preserves the partially prepared instance for explicit operator recovery.
    """
    if os.name != 'nt' or type(runtime) is not LocalRuntime or runtime.profile != 'conversation-d1' or runtime.root.exists():
        raise UpgradeRejected()
    runtime.initialize(pg_root)
    runtime.start()
    from .native_setup import NativeSetup
    setup = NativeSetup(runtime, development=True)
    try:
        setup.handle({'operation': 'development_access'})
    finally:
        setup.close()
    return upgrade_workspace_chat(runtime)


def described(runtime):
    return descriptor(runtime, source_profile="workbench-d2", target_profile="workspace-chat-d3")


def verify_upgrade_receipt(runtime):
    current, (source, target) = described(runtime)
    plan = load_plan(runtime, source, target, journal=JOURNAL, kind=KIND)
    if current.profile != "workspace-chat-d3" or plan is None:
        raise UpgradeRejected()
    return plan


def upgrade_workspace_chat(runtime):
    if os.name != "nt" or type(runtime) is not LocalRuntime or runtime.profile not in ("conversation-d1", "workbench-d2", "workspace-chat-d3"):
        raise UpgradeRejected()
    if runtime.profile == "conversation-d1":
        runtime = upgrade_workbench(runtime)  # Independently verified D1→D2 checkpoint retained.
    current, (source, target) = described(runtime)
    plan = load_plan(current, source, target, journal=JOURNAL, kind=KIND)
    known_service_stopped(current)
    database, target_database = current.database("migrator"), None
    try:
        with database.engine.connect() as connection:
            for key in (607103028, 607103027, 607103018, 607103017):
                if not connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar_one():
                    raise UpgradeRejected()
            connection.commit()
            with connection.begin():
                head = connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one()
                row, restrictions = native_anchor(connection, current)
                no_clients(connection)
                if head == "0028":
                    from .workspace_local_runtime import surface
                    surface(connection)
                    if plan is None or plan["owner_id"] != str(row["owner_id"]) or plan["workspace_id"] != str(row["workspace_id"]):
                        raise UpgradeRejected()
                    if current.profile == "workspace-chat-d3":
                        return current
                    if business_digest(SyntheticBackup._inventory(connection, profile="workbench-d2")) != plan["business"]:
                        raise UpgradeRejected()
                    if connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_thread) OR EXISTS(SELECT 1 FROM class_os.workspace_chat_turn) OR EXISTS(SELECT 1 FROM class_os.workspace_chat_audit)")).scalar_one():
                        raise UpgradeRejected()
                elif head != "0027" or current.profile != "workbench-d2":
                    raise UpgradeRejected()
            if head == "0027":
                from .workbench_local_runtime import surface as old_surface
                with connection.begin():
                    old_surface(connection)
                backup = SyntheticBackup(current, profile="workbench-d2")
                artifact = backup.create()
                backup.check_current_restrictions(artifact, restrictions)
                packet, _ = backup._open(artifact)
                prepared = {"kind": KIND, "root": digest(str(current.root).encode("utf-8")), "source": digest(source), "target": digest(target),
                    "attempt_id": str(uuid4()), "backup_id": str(artifact), "business": business_digest(packet["inventory"]),
                    "owner_id": str(row["owner_id"]), "workspace_id": str(row["workspace_id"])}
                save_plan(current, prepared, plan, journal=JOURNAL); plan = prepared
                target_database = Database(database.engine.url, migration=True, profile="workspace-chat-d3")
                with connection.begin():
                    no_clients(connection); native_anchor(connection, current); old_surface(connection)
                    if SyntheticBackup._inventory(connection, profile="workbench-d2") != packet["inventory"]:
                        raise UpgradeRejected()
                    migrate(target_database, connection=connection)
                    from .workspace_local_runtime import surface
                    surface(connection)
                    if business_digest(SyntheticBackup._inventory(connection, profile="workbench-d2")) != plan["business"]:
                        raise UpgradeRejected()
            if read_bytes(current.manifest, 16384) != source:
                raise UpgradeRejected()
            publish_manifest(current, target)
            return LocalRuntime(current.root, profile="workspace-chat-d3")
    except Exception:
        raise UpgradeRejected() from None
    finally:
        if target_database is not None:
            target_database.close()
        database.close()
