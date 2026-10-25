"""Closed projected reads and artifact INSERT inside existing D1 Gateways."""
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.exit_package import CORE_COLUMNS, PRIMARY_KEYS, AUDIT_COLUMNS, ExitArtifact
from class_os.domain.roster import Receipt
from class_os.domain.conversation_exit import (CONVERSATION_KEYS, MAX_BYTES, MAX_ROWS,
    CreateConversationExit, ConversationExitSummary)
from class_os.domain.conversation_exit_v3 import CONVERSATION_COLUMNS
from class_os.domain.conversation_exit_v5 import build_package, validate_v5
from class_os.domain.recovery_admission import RECOVERY_COLUMNS, RECOVERY_KEYS
from .conversation_control import ConversationBusinessStore, ConversationTransaction
from .conversation_integrity import validate_conversation_integrity
from .conversation_restrictions import RestrictionUnavailable


class ConversationExitStore(ConversationBusinessStore):
    def _conversation_transaction(self, connection):
        return ConversationExitTransaction(connection, self)


class ConversationExitTransaction(ConversationTransaction):
    def _proof(self, binding):
        try:
            _, head = self._anchor(binding)
            compared = self._store.restrictions.compare(head)
            if compared.state != "aligned":
                raise CommandRejected()
            return {"authority_id": str(head.authority_id), "epoch": head.epoch, "source_head_hash": head.digest,
                    "markers": [marker.canonical() for marker in compared.snapshot.markers]}
        except RestrictionUnavailable:
            raise CommandRejected() from None

    def _collection(self, binding, table, columns, keys, budget):
        # Every identifier originates in one of the two fixed registries below,
        # or the fixed audit projection. Never read to_jsonb of the full audit
        # row: runtime must not gain SELECT on session_digest/private columns.
        projection = "SELECT " + ",".join(columns) + " FROM class_os." + table + " WHERE workspace_id=:w"
        count, size = self._connection.execute(text("SELECT count(*),coalesce(sum(octet_length(to_jsonb(q)::text)),0) FROM (" +
            projection + " LIMIT 10001) q"), {"w": binding["workspace_id"]}).one()
        budget[0] += size
        if count > MAX_ROWS or budget[0] > MAX_BYTES:
            raise CommandRejected()
        rows = self._connection.execute(text(projection + " ORDER BY " + ",".join(keys) + " LIMIT 10001"),
                                        {"w": binding["workspace_id"]}).mappings().all()
        if len(rows) != count:
            raise CommandRejected()
        return [{key: str(value) if isinstance(value, UUID) else value.isoformat() if isinstance(value, (date, datetime)) else value
                 for key, value in row.items()} for row in rows]

    def _snapshot(self, binding, now):
        proof = self._proof(binding)
        validate_conversation_integrity(self._connection)
        budget = [0]
        core = {table: self._collection(binding, table, columns, PRIMARY_KEYS[table], budget) for table, columns in CORE_COLUMNS.items()}
        conversations = {table: self._collection(binding, table, columns, CONVERSATION_KEYS[table], budget)
                         for table, columns in CONVERSATION_COLUMNS.items()}
        recovery = {table: self._collection(binding, table, columns, RECOVERY_KEYS[table], budget)
                    for table, columns in RECOVERY_COLUMNS.items()}
        # Validate clear markers against every exported thread, not only the
        # selected screen. No hidden old-body replay behind a current anchor.
        build_package(binding["workspace_id"], binding["actor_id"], now, core, conversations, proof, [], recovery)
        return core, conversations, proof, recovery, budget

    def conversation_exit_summary(self, binding, now):
        core, conversations, proof, recovery, _ = self._snapshot(binding, now)
        from class_os.domain.conversation_exit_v4 import snapshot_hash as current_hash
        return ConversationExitSummary(current_hash(core, conversations, proof, recovery),
                                       {key: len(rows) for key, rows in {**core, **conversations, **recovery}.items()}, proof["epoch"])

    def validate_conversation_exit(self, binding, command, now):
        if (self.export_exists(binding["workspace_id"], command.export_id)
                or self.conversation_exit_summary(binding, now).snapshot_hash != command.expected_snapshot_hash):
            raise CommandRejected()

    def apply(self, binding, command, now):
        if type(command) is not CreateConversationExit:
            return super().apply(binding, command, now)
        self.validate_conversation_exit(binding, command, now)
        core, conversations, proof, recovery, budget = self._snapshot(binding, now)
        audit = self._collection(binding, "business_audit", AUDIT_COLUMNS, ("occurred_at", "event_id"), budget)
        bundle = build_package(binding["workspace_id"], binding["actor_id"], now, core, conversations, proof, audit, recovery)
        self._mutate(text("""INSERT INTO class_os.export_job
            (workspace_id,export_id,actor_id,package_hash,bundle,created_at,expires_at,state)
            VALUES(:workspace_id,:id,:actor_id,:hash,:bundle,:now,:expires,'ready')"""),
            {**binding, "id": command.export_id, "hash": bundle["package_checksum"], "bundle": Jsonb(bundle),
             "now": now, "expires": now + timedelta(minutes=30)})
        return Receipt(uuid4(), command.export_id, 1)

    def conversation_exit_artifact(self, binding, export_id, now):
        proof = self._proof(binding)
        row = self._connection.execute(text("""SELECT package_hash,bundle FROM class_os.export_job
            WHERE workspace_id=:workspace_id AND actor_id=:actor_id AND export_id=:id AND state='ready' AND :now<expires_at"""),
            {**binding, "id": export_id, "now": now}).mappings().one_or_none()
        if row is None:
            raise CommandRejected()
        bundle = row["bundle"]
        try:
            if bundle.get("restriction_evidence") != proof:
                raise CommandRejected()
            validate_v5(bundle)
            if row["package_hash"] != bundle["package_checksum"]:
                raise CommandRejected()
        except (ValueError, TypeError, AttributeError):
            raise CommandRejected() from None
        return ExitArtifact(export_id, row["package_hash"], bundle)
