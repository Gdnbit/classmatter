"""Fixed admission SQL and body attribution behind existing QG/BCG/ISB."""
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.application.recovery_admission import (AuthorizedRetirementReader, AdmissionSummary, BODY_ACTIONS,
    COMMAND_ACTIONS, admission_operation_permitted, attributed_read_permitted)
from class_os.domain.recovery_admission import (AdmitConversationTarget, AdmissionFence, ADMISSION_COLUMNS,
    origins_hash, source_audit_hash, decode_admission)
from class_os.domain.recovery_results import make_origins, ENTITY_KEYS
from class_os.domain.exit_package import checksum
from class_os.domain.roster import Receipt
from class_os.domain.conversation_control import ConversationHistory
from class_os.domain.conversation_results import ProducedResult
from class_os.domain.conversation_exit_v6 import build_package
from class_os.domain.target_import import IMPORT_COLUMNS
from .target_import_store import TargetImportTransaction, validate_projection_budget
from .conversation_exit import ConversationExitStore, ConversationExitTransaction
from .recovery_admission import ProtectedTargetAdmission, AdmissionUnavailable
from .target_import import ProtectedTargetImport
from .recovery_commit_evidence import require_recovery_commit
from .conversation_interaction import InteractionTransaction
from .conversation_worker import WorkerTransaction


def admission_boundary(tx, binding, action, proposal_id):
    """Return true only for a fully committed, local, current admission."""
    port = ProtectedTargetAdmission(tx._store.restrictions)
    rows = tx._connection.execute(text("SELECT workspace_id FROM class_os.conversation_admission WHERE workspace_id=:workspace_id"), binding).all()
    if not rows:
        # File-only evidence never grants ordinary access. The pending-target
        # boundary still checks the exact original import/proposal for retries.
        if port.present():
            port.read()
        return False
    try:
        fence = port.read()
        imported = ProtectedTargetImport(tx._store.restrictions).read()
        if (fence.workspace_id != binding["workspace_id"] or fence.stage.fence.owner_id != binding["actor_id"]
                or fence.stage.fence != imported):
            raise CommandRejected()
        reader = ConversationExitTransaction(tx._connection, tx._store)
        core, conversations, proof, recovery, _ = reader._snapshot(binding, tx._now_for_admission())
        anchors = recovery["conversation_admission"]
        if len(anchors) != 1 or anchors[0] != fence.anchor(port.digest(fence)):
            raise CommandRejected()
        receipt = tx._connection.execute(text("""SELECT r.receipt_id,r.resource_version,r.committed_at,p.payload
            FROM class_os.command_receipt r JOIN class_os.command_proposal p USING(proposal_id)
            WHERE r.workspace_id=:workspace_id AND r.actor_id=:actor_id AND r.receipt_id=:receipt
            AND r.resource_id=:attempt AND p.command_type='conversation.import.admit' AND p.state='committed'"""),
            {**binding, "receipt": fence.receipt_id, "attempt": fence.command.attempt_id}).mappings().one_or_none()
        if (receipt is None or receipt["resource_version"] != 3 or receipt["payload"] != fence.command.canonical()
                or receipt["committed_at"] < fence.created_at):
            raise CommandRejected()
        require_recovery_commit(tx._connection, binding, fence.command, fence.receipt_id, 3, fence.created_at)
        require_recovery_commit(tx._connection, binding, imported.command, fence.stage.receipt_id, 1, imported.created_at)
        if action in BODY_ACTIONS and (type(tx) is not AdmissionTransaction or not attributed_read_permitted(tx._store, binding, action)):
            raise CommandRejected()
        if action in COMMAND_ACTIONS and (type(tx) is not AdmissionTransaction or not admission_operation_permitted(tx._store, binding, action, proposal_id)):
            raise CommandRejected()
        return True
    except (ValueError, AdmissionUnavailable):
        raise CommandRejected() from None


class AdmissionStore(ConversationExitStore):
    def __init__(self, database, restrictions, retirement=None):
        if retirement is not None and type(retirement) is not AuthorizedRetirementReader:
            raise ValueError("Live authorized retirement reader required")
        super().__init__(database, restrictions)
        self.retirement = retirement

    def _conversation_transaction(self, connection):
        return AdmissionTransaction(connection, self)


@dataclass(frozen=True)
class HistoricalResult:
    message_id: UUID
    result: ProducedResult
    content_authority: str = "assistant-unverified"
    draft_status: str = "uncommitted"


@dataclass(frozen=True)
class AuthorAwareHistory:
    history: ConversationHistory
    thread_attribution: dict
    message_attributions: tuple[dict, ...]
    results: tuple[HistoricalResult, ...] = ()


@dataclass(frozen=True)
class HistoryPage:
    value: AuthorAwareHistory
    next_before: int | None


class AdmissionTransaction(WorkerTransaction, InteractionTransaction, TargetImportTransaction):
    def has_committed_admission(self, binding):
        return self._connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.conversation_admission WHERE workspace_id=:workspace_id)"), binding).scalar_one()

    def admission_summary(self, binding, attempt_id, now):
        stage = self.committed_stage(binding, attempt_id)
        core, conversations, _, recovery, _ = self._snapshot(binding, now)
        rows = make_origins(core, conversations, recovery)
        return AdmissionSummary(attempt_id, stage.snapshot_hash, origins_hash(rows), len(rows))

    def validate_admission(self, binding, command, now):
        if type(command) is not AdmitConversationTarget or self._store.retirement is None or self.has_committed_admission(binding):
            raise CommandRejected()
        try:
            stage = self.committed_stage(binding, command.attempt_id)
            retired = self._store.retirement.current()
            if retired.fence.stage != stage:
                raise CommandRejected()
            core, conversations, proof, recovery, _ = self._snapshot(binding, now)
            rows = make_origins(core, conversations, recovery)
            if origins_hash(rows) != command.expected_origins_hash:
                raise CommandRejected()
            port = ProtectedTargetAdmission(self._store.restrictions)
            batch_digest = checksum(recovery["conversation_import"][0])
            audit_digest = source_audit_hash(recovery["conversation_source_audit"])
            fence = AdmissionFence(retired, command, len(rows), batch_digest, audit_digest, uuid4(), now)
            if port.present():
                prior = port.read()
                if (prior.retirement != retired or prior.command != command or prior.origin_count != len(rows)
                        or prior.batch_hash != batch_digest or prior.source_audit_hash != audit_digest
                        or not retired.fence.created_at <= prior.created_at <= now):
                    raise CommandRejected()
                fence = prior
            projected = {**recovery, "conversation_admission": [fence.anchor(port.digest(fence))], "conversation_origin": rows}
            build_package(binding["workspace_id"], binding["actor_id"], now, core, conversations, proof, [], projected, verify_receipts=False)
            validate_projection_budget(self._connection, (core, conversations, proof, projected))
            return fence, rows
        except (ValueError, AdmissionUnavailable):
            raise CommandRejected() from None

    def apply(self, binding, command, now):
        if type(command) is not AdmitConversationTarget:
            from class_os.domain.conversation_interaction import CreateConversation, RenameConversation, ArchiveConversation, EnqueueConversation
            from class_os.domain.conversation_worker import ClaimRun, FinishRun, CancelRun, ReconcileRun
            from class_os.domain.conversation_results import FinishResult
            result = (self.apply_worker(binding, command, now) if type(command) in (ClaimRun, FinishRun, CancelRun, ReconcileRun, FinishResult)
                      else self.apply_interaction(binding, command, now) if type(command) in
                      (CreateConversation, RenameConversation, ArchiveConversation, EnqueueConversation)
                      else super().apply(binding, command, now))
            try:
                self._snapshot(binding, now)
            except Exception:
                raise RuntimeError("Post-admission write verification failed; SQL must roll back") from None
            return result
        fence, origins = self.validate_admission(binding, command, now)
        port = ProtectedTargetAdmission(self._store.restrictions)
        try:
            digest = port.publish(fence)
        except AdmissionUnavailable:
            raise CommandRejected() from None
        self._insert("conversation_admission", ADMISSION_COLUMNS["conversation_admission"], fence.anchor(digest))
        for row in origins:
            self._insert("conversation_origin", ADMISSION_COLUMNS["conversation_origin"], row)
        try:
            self._snapshot(binding, now)
        except Exception:
            raise RuntimeError("Admission verification failed; SQL must roll back") from None
        return Receipt(fence.receipt_id, command.attempt_id, 3)

    def _attribution_snapshot(self, workspace, now):
        owner = self._connection.execute(text("SELECT owner_id FROM class_os.conversation_control WHERE workspace_id=:w"), {"w": workspace}).scalar_one()
        return owner, self._snapshot({"workspace_id": workspace, "actor_id": owner}, now)

    @staticmethod
    def _attribution(snapshot, owner, kind, resource, version, thread=None):
        core, conversations, _, recovery, _ = snapshot
        collection = core if kind in core else conversations
        current = next(row for row in collection[kind] if row[ENTITY_KEYS[kind]] == str(resource)
                       and (kind != "record_revision" or row["version"] == version)
                       and (thread is None or row.get("thread_id") == str(thread)))
        origin = next((row for row in recovery["conversation_origin"] if row["entity_kind"] == kind
                       and row["resource_id"] == str(resource) and (kind != "record_revision" or row["source_version"] == version)
                       and row["thread_id"] == (str(thread) if thread is not None else None)), None)
        batch = recovery["conversation_import"][0] if origin is not None else None
        author = batch["source_owner_id"] if batch else str(owner)
        editor = author if origin is not None and current.get("version", 0) == origin["source_version"] else str(owner)
        if origin is not None and kind == "student_identifier" and current["valid_to"] is not None and origin["source_open"]:
            editor = str(owner)  # Existing identifier closure has no version field.
        assistant = kind == "conversation_message" and current["role"] == "assistant"
        return {"origin": "source-import" if origin else "local-owner", "created_by": None if assistant else author,
                "last_modified_by": None if assistant else editor, "source_workspace_id": batch["source_workspace_id"] if batch else None,
                "source_owner_id": batch["source_owner_id"] if batch else None,
                "source_version": origin["source_version"] if origin else None,
                "content_authority": "assistant-unverified" if assistant else "user-original" if kind == "conversation_message" else "domain-data"}

    def activity(self, workspace, class_id, term_id, now, *, student_id=None):
        value = super().activity(workspace, class_id, term_id, now, student_id=student_id)
        owner, snapshot = self._attribution_snapshot(workspace, now)
        return {**value, "records": tuple({**row, "attribution": self._attribution(snapshot, owner, "record_revision", row["record_id"], row["version"])} for row in value["records"]),
                "tasks": tuple({**row, "attribution": self._attribution(snapshot, owner, "manual_task", row["task_id"], row["version"])} for row in value["tasks"])}

    def conversation_history(self, binding, class_id, term_id, thread_id):
        return self.conversation_page(binding, class_id, term_id, thread_id).value

    def conversation_page(self, binding, class_id, term_id, thread_id, *, before_ordinal=None, expected_version=None):
        history = super().conversation_history(binding, class_id, term_id, thread_id,
            before_ordinal=before_ordinal, expected_version=expected_version)
        snapshot = self._snapshot(binding, self._now_for_admission())
        attribution = self._attribution(snapshot, binding["actor_id"], "conversation_thread", thread_id, history.version)
        messages = tuple({"message_id": str(row.message_id), "attribution": self._attribution(snapshot, binding["actor_id"],
            "conversation_message", row.message_id, 0, thread_id)} for row in history.messages)
        from class_os.domain.conversation_exit_v6 import result_value
        from class_os.domain.conversation_result_integrity import validate_result_rows, message_key
        core, conversations, proof, recovery, budget = snapshot
        visible = {str(item.message_id) for item in history.messages if item.content.role == "assistant"}
        # Presence of sidecars or an intact proposal is not an authority flag:
        # deleting both must never downgrade a completed typed outcome to text.
        now = self._now_for_admission()
        self.verified_result_bundle(binding, now, snapshot)
        results = []
        groups = validate_result_rows(conversations, str(binding["workspace_id"]), now.isoformat())
        threads = {item["thread_id"]: item for item in conversations["conversation_thread"]}
        for message in conversations["conversation_message"]:
            if (message["message_id"] in visible and message_key(message) in groups
                    and groups[message_key(message)]["receipt"]["protocol"] == "fixed-result"):
                results.append(HistoricalResult(UUID(message["message_id"]), result_value(threads[message["thread_id"]], message, groups[message_key(message)])))
        selected = {row.turn_id for row in history.messages}
        ordinals = [row["ordinal"] for row in conversations["conversation_turn"]
                    if row["thread_id"] == str(thread_id) and UUID(row["turn_id"]) in selected]
        return HistoryPage(AuthorAwareHistory(history, attribution, messages, tuple(results)),
                           min(ordinals) if history.truncated else None)
