"""Fixed target INSERTs, provenance and audit inside the existing BCG UoW."""
from datetime import datetime, date
from uuid import UUID, uuid4

from sqlalchemy import text
from psycopg.types.json import Jsonb

from class_os.application.roster import CommandRejected
from class_os.application.target_import import AuthorizedSourceReader, target_operation_permitted
from class_os.domain.target_import import (RecoveryCandidate, StageConversationImport, TargetFence,
    ENTITY_KEYS, IMPORT_COLUMNS, provenance_rows)
from class_os.domain.exit_package import CORE_COLUMNS
from class_os.domain.conversation_exit_v3 import CONVERSATION_COLUMNS
from class_os.domain.conversation_exit import MAX_BYTES
from class_os.domain.roster import Receipt
from class_os.domain.conversation_exit_v4 import build_package
from .conversation_exit import ConversationExitStore, ConversationExitTransaction
from .conversation_restrictions import ClearMarker, RestrictionUnavailable
from .target_import import ProtectedTargetImport, ImportUnavailable


def validate_projection_budget(connection, projected):
    """Use the same PG JSONB row-text bytes as the subsequent fixed reader."""
    rows = [row for collections in (projected[0], projected[1], projected[3])
            for collection in collections.values() for row in collection]
    size = connection.execute(text("""SELECT coalesce(sum(octet_length(value::text)),0)
        FROM jsonb_array_elements(CAST(:rows AS jsonb)) AS item(value)"""), {"rows": Jsonb(rows)}).scalar_one()
    if size > MAX_BYTES:
        raise CommandRejected()


def validate_import_integrity(connection):
    """Snapshot relation/provenance checks only, never freshness or admission."""
    rows = connection.execute(text("SELECT workspace_id,restorer_id,imported_at FROM class_os.conversation_import LIMIT 2")).mappings().all()
    if not rows:
        if any(connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os." + table + ")")).scalar_one()
               for table in ("conversation_provenance", "conversation_source_audit")):
            raise ValueError("Orphan import evidence")
        return
    if len(rows) != 1:
        raise ValueError("Unsupported import scope")
    from class_os.domain.exit_package import PRIMARY_KEYS
    from class_os.domain.conversation_exit import CONVERSATION_KEYS
    from class_os.domain.target_import import IMPORT_KEYS
    row = rows[0]
    binding, budget = {"workspace_id": row["workspace_id"]}, [0]
    reader = ConversationExitTransaction(connection, None)
    core = {k: reader._collection(binding, k, v, PRIMARY_KEYS[k], budget) for k, v in CORE_COLUMNS.items()}
    conversations = {k: reader._collection(binding, k, v, CONVERSATION_KEYS[k], budget) for k, v in CONVERSATION_COLUMNS.items()}
    recovery = {k: reader._collection(binding, k, v, IMPORT_KEYS[k], budget) for k, v in IMPORT_COLUMNS.items()}
    if len(conversations["conversation_control"]) != 1:
        raise ValueError("Missing import control")
    control = conversations["conversation_control"][0]
    markers = [{"thread_id": r["thread_id"], "version_after": r["version"], "restricted_at": r["cleared_at"]}
               for r in conversations["conversation_thread"] if r["status"] == "cleared"]
    markers.sort(key=lambda r: (r["restricted_at"], r["thread_id"]))
    proof = {"authority_id": control["authority_id"], "epoch": control["epoch"], "source_head_hash": control["head_hash"], "markers": markers}
    build_package(row["workspace_id"], row["restorer_id"], row["imported_at"], core, conversations, proof, [], recovery)


def target_boundary(tx, binding, action, proposal_id):
    """Check before every native D1 boundary; never trust an absent file alone."""
    port = ProtectedTargetImport(tx._store.restrictions)
    row = tx._connection.execute(text("""SELECT attempt_id,restorer_id,target_binding,package_hash,source_fence_hash,source_receipt_id FROM class_os.conversation_import
        WHERE workspace_id=:workspace_id"""), binding).mappings().one_or_none()
    try:
        present = port.present()
        if not present and row is None:
            return False
        if not target_operation_permitted(tx._store, binding, action, proposal_id):
            raise CommandRejected()
        fence = port.read()  # SQL pending + missing/corrupt file is never an exemption.
        anchor = tx._connection.execute(text("""SELECT owner_id,authority_id,epoch,head_hash FROM class_os.conversation_control
            WHERE workspace_id=:workspace_id"""), binding).mappings().one_or_none()
        snapshot = tx._store.restrictions.read()
        root_binding = tx._store.restrictions._binding(tx._store.restrictions._root())
        if (anchor is None or anchor["owner_id"] != binding["actor_id"] or fence.owner_id != binding["actor_id"]
                or fence.workspace_id != binding["workspace_id"] or anchor["authority_id"] != fence.authority_id
                or snapshot.head.authority_id != fence.authority_id
                or tx._store.restrictions._snapshot(tx._store.restrictions._root(), fence.authority_id, ()).head.digest != fence.initial_head_hash
                or row is not None and (row["attempt_id"] != fence.command.attempt_id or row["restorer_id"] != binding["actor_id"]
                    or row["target_binding"] != root_binding or row["package_hash"] != fence.command.package_hash
                    or row["source_fence_hash"] != fence.command.source_fence_hash or row["source_receipt_id"] != fence.source_receipt_id
                    or anchor["epoch"] != snapshot.head.epoch or anchor["head_hash"] != snapshot.head.digest)):
            raise CommandRejected()
        if action not in ("command.preview", "conversation.transfer.proof"):
            proposal = tx.proposal(binding["workspace_id"], proposal_id)
            if not proposal or proposal["actor_id"] != binding["actor_id"] or proposal["payload"] != fence.command.canonical():
                raise CommandRejected()
        return True
    except (ImportUnavailable, RestrictionUnavailable):
        raise CommandRejected() from None


class TargetImportStore(ConversationExitStore):
    def __init__(self, database, restrictions, candidate, source):
        if type(candidate) is not RecoveryCandidate or type(source) is not AuthorizedSourceReader:
            raise ValueError("Fixed candidate and live authorized source reader required")
        super().__init__(database, restrictions)
        self.candidate, self.source = candidate, source

    def _conversation_transaction(self, connection):
        return TargetImportTransaction(connection, self)


def sql_value(key, value):
    if value is None:
        return None
    if key.endswith("_id") or key in ("created_by", "updated_by", "recorded_by", "restorer_id"):
        return UUID(value) if type(value) is str else value
    if key.endswith("_at") or key in ("valid_from", "valid_to", "lease_until", "queued_until"):
        return datetime.fromisoformat(value) if type(value) is str else value
    if key in ("start_date", "end_date"):
        return date.fromisoformat(value) if type(value) is str else value
    return value


class TargetImportTransaction(ConversationExitTransaction):
    def committed_stage(self, binding, attempt_id):
        from class_os.domain.source_retirement import CommittedStage
        from class_os.domain.conversation_exit_v4 import snapshot_hash
        try:
            port = ProtectedTargetImport(self._store.restrictions)
            fence = port.read()
            batch = self._connection.execute(text("""SELECT imported_at FROM class_os.conversation_import
                WHERE workspace_id=:workspace_id AND restorer_id=:actor_id AND attempt_id=:attempt AND phase='pending'"""),
                {**binding, "attempt": attempt_id}).mappings().one_or_none()
            receipts = self._connection.execute(text("""SELECT r.receipt_id,r.resource_version,p.payload
                FROM class_os.command_receipt r JOIN class_os.command_proposal p USING(proposal_id)
                WHERE r.workspace_id=:workspace_id AND r.actor_id=:actor_id AND r.resource_id=:attempt
                AND p.command_type='conversation.import.stage' AND p.state='committed' LIMIT 2"""),
                {**binding, "attempt": attempt_id}).mappings().all()
            if (batch is None or len(receipts) != 1 or fence.command.attempt_id != attempt_id
                    or receipts[0]["resource_version"] != 1 or receipts[0]["payload"] != fence.command.canonical()):
                raise CommandRejected()
            core, conversations, proof, recovery, _ = self._snapshot(binding, batch["imported_at"])
            packet = port._packet(self._store.restrictions._root(), fence)
            from class_os.domain.exit_package import checksum
            return CommittedStage(fence, checksum(packet), receipts[0]["receipt_id"],
                                  self._store.restrictions._binding(self._store.restrictions._root()),
                                  snapshot_hash(core, conversations, proof, recovery), batch["imported_at"])
        except (ImportUnavailable, RestrictionUnavailable, ValueError):
            raise CommandRejected() from None

    def validate_target_import(self, binding, command, now):
        try:
            restrictions = self._store.restrictions
            root_binding = restrictions._binding(restrictions._root())
            anchor = self._connection.execute(text("""SELECT authority_id,epoch,head_hash,created_at,updated_at,transfer_id,transfer_hash,transfer_at FROM class_os.conversation_control
                WHERE workspace_id=:workspace_id AND owner_id=:actor_id"""), binding).mappings().one_or_none()
            if (anchor is None or anchor["transfer_id"] is not None or anchor["epoch"] != 0 or anchor["updated_at"] > now
                    or self._connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.conversation_import WHERE workspace_id=:workspace_id)"), binding).scalar_one()):
                raise CommandRejected()
            for table in (*ENTITY_KEYS, "export_job", "model_configuration"):
                if self._connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os." + table + " WHERE workspace_id=:workspace_id)"), binding).scalar_one():
                    raise CommandRejected()
            # Refuse already-staged targets before acquiring a peer lock.
            # Retirement observes committed targets in the reverse direction.
            source = self._store.source.current()
            bundle = self._store.candidate.match(command, source, binding["workspace_id"], binding["actor_id"], root_binding, now)
            current = restrictions.read()
            markers = tuple(ClearMarker(UUID(m["thread_id"]), m["version_after"], datetime.fromisoformat(m["restricted_at"]))
                            for m in bundle["restriction_evidence"]["markers"])
            if (current.head.authority_id != anchor["authority_id"] or current.markers != markers[:len(current.markers)]
                    or len(current.markers) > len(markers)):
                raise CommandRejected()
            fence = TargetFence(binding["workspace_id"], binding["actor_id"], anchor["authority_id"], anchor["head_hash"],
                                command, source.receipt_id, now)
            port = ProtectedTargetImport(restrictions)
            if port.present():
                prior = port.read()
                if (prior.command != command or prior.workspace_id != fence.workspace_id or prior.owner_id != fence.owner_id
                        or prior.authority_id != fence.authority_id or prior.initial_head_hash != fence.initial_head_hash
                        or prior.source_receipt_id != source.receipt_id or not anchor["updated_at"] <= prior.created_at <= now):
                    raise CommandRejected()
                fence = prior
            elif current.markers or current.head.digest != anchor["head_hash"]:
                raise CommandRejected()
            projected = self._project(binding, bundle, source, fence, anchor, markers, now)
            # Expanded provenance/metadata must fit before publishing any fence.
            build_package(binding["workspace_id"], binding["actor_id"], now, *projected[:3], [], projected[3])
            validate_projection_budget(self._connection, projected)
            return fence, markers, projected
        except (ValueError, ImportUnavailable, RestrictionUnavailable):
            raise CommandRejected() from None

    def _insert(self, table, columns, row):
        # Identifiers only originate in the fixed registries owned above.
        self._mutate(text("INSERT INTO class_os." + table + " (" + ",".join(columns) + ") VALUES (" +
                          ",".join(":" + c for c in columns) + ")"), {k: sql_value(k, row[k]) for k in columns})

    def _project(self, binding, bundle, source, fence, anchor, markers, now):
        restrictions = self._store.restrictions
        head = restrictions._snapshot(restrictions._root(), anchor["authority_id"], markers).head
        command = fence.command
        batch = {"workspace_id": str(binding["workspace_id"]), "attempt_id": str(command.attempt_id), "restorer_id": str(binding["actor_id"]),
            "source_workspace_id": str(source.fence.workspace_id), "source_owner_id": str(source.fence.owner_id),
            "source_authority_id": str(source.fence.authority_id), "source_epoch": source.fence.restriction_epoch,
            "source_head_hash": source.fence.restriction_hash, "source_fence_hash": source.fence_hash,
            "source_receipt_id": str(source.receipt_id), "source_root_binding": source.root_binding,
            "package_hash": command.package_hash, "target_binding": source.fence.command.target_binding,
            "source_sealed_at": source.fence.created_at.isoformat(), "imported_at": now.isoformat(), "phase": "pending"}
        core = {"workspace": self._collection(binding, "workspace", CORE_COLUMNS["workspace"], ("workspace_id",), [0])}
        conversations = {}
        for kind in ENTITY_KEYS:
            destination = core if kind in CORE_COLUMNS else conversations
            destination[kind] = []
            for original in bundle["core" if kind in CORE_COLUMNS else "conversations"][kind]:
                row = {**original, "workspace_id": str(binding["workspace_id"])}
                for author in ("created_by", "updated_by", "recorded_by", "owner_id"):
                    if author in row:
                        row[author] = str(binding["actor_id"])
                destination[kind].append(row)
        conversations["conversation_control"] = [{"workspace_id": str(binding["workspace_id"]), "owner_id": str(binding["actor_id"]),
            "authority_id": str(head.authority_id), "epoch": head.epoch, "head_hash": head.digest,
            "created_at": anchor["created_at"].isoformat(), "updated_at": now.isoformat(),
            "transfer_id": None, "transfer_hash": None, "transfer_at": None}]
        proof = {"authority_id": str(head.authority_id), "epoch": head.epoch, "source_head_hash": head.digest,
                 "markers": [m.canonical() for m in markers]}
        recovery = {"conversation_import": [batch],
            "conversation_provenance": provenance_rows(bundle, binding["workspace_id"], command.attempt_id),
            "conversation_source_audit": [{**row, "workspace_id": str(binding["workspace_id"]), "attempt_id": str(command.attempt_id),
                "source_workspace_id": str(source.fence.workspace_id)} for row in bundle["audit_refs"]]}
        return core, conversations, proof, recovery

    def apply(self, binding, command, now):
        if type(command) is not StageConversationImport:
            return super().apply(binding, command, now)
        fence, markers, projected = self.validate_target_import(binding, command, now)
        restrictions = self._store.restrictions
        try:
            ProtectedTargetImport(restrictions).stage(fence)
            snapshot = restrictions.read()
            for marker in markers[len(snapshot.markers):]:
                restrictions.advance(snapshot.head, marker)
                snapshot = restrictions.read()
        except (ImportUnavailable, RestrictionUnavailable):
            raise CommandRejected() from None
        core, conversations, _, recovery = projected
        self._insert("conversation_import", IMPORT_COLUMNS["conversation_import"], recovery["conversation_import"][0])
        for kind in ENTITY_KEYS:
            collection = core if kind in CORE_COLUMNS else conversations
            columns = CORE_COLUMNS[kind] if kind in CORE_COLUMNS else CONVERSATION_COLUMNS[kind]
            for row in collection[kind]:
                self._insert(kind, columns, row)
        for row in recovery["conversation_provenance"]:
            self._insert("conversation_provenance", IMPORT_COLUMNS["conversation_provenance"], row)
        for row in recovery["conversation_source_audit"]:
            self._insert("conversation_source_audit", IMPORT_COLUMNS["conversation_source_audit"], row)
        self._mutate(text("""UPDATE class_os.conversation_control SET epoch=:epoch,head_hash=:head,updated_at=:at
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND epoch=0 AND head_hash=:initial AND transfer_id IS NULL"""),
            {**binding, "epoch": snapshot.head.epoch, "head": snapshot.head.digest, "at": now, "initial": fence.initial_head_hash})
        # Verify the same closed exporter representation before allowing receipt/audit.
        try:
            self._snapshot(binding, now)
        except Exception:
            # A late validation/IO denial must roll back all prior INSERTs,
            # not be converted into a committed denied-audit transaction.
            raise RuntimeError("Staged import verification failed; SQL must roll back") from None
        return Receipt(uuid4(), command.attempt_id, 1)
