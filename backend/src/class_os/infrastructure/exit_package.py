"""Fixed snapshot collections behind the existing business transaction."""
from datetime import date, datetime, timedelta
import json
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from sqlalchemy import text

from class_os.domain.exit_package import CORE_COLUMNS, PRIMARY_KEYS, AUDIT_COLUMNS, MISSING_LIFECYCLE, NONPORTABLE, ExitSummary, ExitArtifact, checksum, validate_package
from class_os.domain.roster import Receipt


class ExitTransaction:
    def core_snapshot(self, workspace):
        core = {}
        for table, columns in CORE_COLUMNS.items():
            # Identifiers come exclusively from the immutable source registry,
            # never request/model input. All values are bound parameters.
            statement = "SELECT " + ",".join(columns) + " FROM class_os." + table + " WHERE workspace_id=:w ORDER BY " + ",".join(PRIMARY_KEYS[table]) + " LIMIT 10001"
            rows = self._connection.execute(text(statement), {"w": workspace}).mappings().all()
            if len(rows) > 10000:
                raise ValueError("Core export exceeds supported synthetic limit")
            core[table] = [{key: str(value) if isinstance(value, UUID) else value.isoformat() if isinstance(value, (date, datetime)) else value
                            for key, value in row.items()} for row in rows]
        return core

    def exit_summary(self, workspace):
        core = self.core_snapshot(workspace)
        return ExitSummary(checksum(core), {key: len(value) for key, value in core.items()})

    def export_exists(self, workspace, export_id):
        return self._connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.export_job WHERE workspace_id=:w AND export_id=:id)"),
                                        {"w": workspace, "id": export_id}).scalar_one()

    def create_exit(self, binding, command, now):
        core = self.core_snapshot(binding["workspace_id"])
        rows = self._connection.execute(text("SELECT " + ",".join(AUDIT_COLUMNS) +
            " FROM class_os.business_audit WHERE workspace_id=:workspace_id AND actor_id=:actor_id ORDER BY occurred_at,event_id LIMIT 10001"), binding).mappings().all()
        if len(rows) > 10000:
            raise ValueError("Audit export exceeds supported synthetic limit")
        audit_refs = [{key: str(value) if isinstance(value, UUID) else value.isoformat() if isinstance(value, datetime) else value for key, value in row.items()} for row in rows]
        bundle = {"schema_version": "class-os.synthetic-core-exit.v1", "purpose": "synthetic-core-recovery",
                  "workspace_id": str(binding["workspace_id"]), "created_at": now.isoformat(), "actor_refs": [str(binding["actor_id"])],
                  "core": core, "core_checksum": checksum(core), "nonportable": list(NONPORTABLE),
                  "lifecycle_status": {"complete": False, "missing": list(MISSING_LIFECYCLE)}, "audit_refs": audit_refs}
        bundle["package_checksum"] = checksum(bundle)
        validate_package(bundle)
        if len(json.dumps(bundle, ensure_ascii=False).encode("utf-8")) > 1048576:
            raise ValueError("Synthetic exit artifact exceeds the supported application limit")
        self._mutate(text("""INSERT INTO class_os.export_job
            (workspace_id,export_id,actor_id,package_hash,bundle,created_at,expires_at,state)
            VALUES(:workspace_id,:export_id,:actor_id,:hash,:bundle,:now,:expires,'ready')"""),
            {**binding, "export_id": command.export_id, "hash": bundle["package_checksum"], "bundle": Jsonb(bundle),
             "now": now, "expires": now + timedelta(minutes=30)})
        return Receipt(uuid4(), command.export_id, 1)

    def exit_artifact(self, binding, export_id, now):
        row = self._connection.execute(text("""SELECT package_hash,bundle FROM class_os.export_job
            WHERE workspace_id=:workspace_id AND actor_id=:actor_id AND export_id=:id AND state='ready' AND :now<expires_at"""),
            {**binding, "id": export_id, "now": now}).mappings().one_or_none()
        if row is None:
            return None
        validate_package(row["bundle"])
        if row["bundle"]["package_checksum"] != row["package_hash"]:
            raise ValueError("Stored exit artifact mismatch")
        return ExitArtifact(export_id, row["package_hash"], row["bundle"])
