"""Fixed D1 SQL inside existing ISB/BCG/QG transactions only."""
from uuid import uuid4
from datetime import datetime, timedelta

from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.conversation_control import InitializeConversationControl, ClearConversation, ConversationHistory, HistoryMessage
from class_os.domain.durable_conversation import VisibleMessage
from class_os.domain.roster import Receipt
from class_os.domain.exit_package import checksum
from .conversation_restrictions import ClearMarker, RestrictionHead, RestrictionUnavailable, FILE_NAME
from .roster import PostgresBusinessStore, BusinessTransaction


class ConversationBusinessStore(PostgresBusinessStore):
    def __init__(self, database, restrictions):
        if database.profile != "conversation-d1":
            raise ValueError("Explicit conversation profile required")
        super().__init__(database)
        self.restrictions = restrictions

    def _transaction(self, connection):
        if connection.execute(text("SELECT version_num FROM class_os.alembic_version")).scalar_one() != "0026":
            raise RuntimeError("Explicit conversation control schema required")
        return self._conversation_transaction(connection)

    def _conversation_transaction(self, connection):
        return ConversationTransaction(connection, self)


class ConversationTransaction(BusinessTransaction):
    def _now_for_admission(self):
        now = getattr(self, "authorized_at", None)
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise CommandRejected()
        return now

    def authorize_boundary(self, binding, action, proposal_id):
        from .target_import_store import target_boundary
        if target_boundary(self, binding, action, proposal_id):
            return
        from class_os.application.source_transfer import source_operation_permitted
        from .source_transfer import ProtectedSourceTransfer, TransferUnavailable
        from .source_retirement import ProtectedSourceRetirement, RetirementUnavailable
        port = ProtectedSourceTransfer(self._store.restrictions)
        row = self._connection.execute(text("""SELECT authority_id,epoch,head_hash,transfer_id FROM class_os.conversation_control
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id"""), binding).mappings().one_or_none()
        try:
            if row is not None:
                # Verify the injected root against the existing DB authority,
                # including a valid pending-clear prefix. A fresh/wrong root
                # cannot hide a file-first fence after SQL rollback.
                self._store.restrictions.compare(RestrictionHead(row["authority_id"], binding["workspace_id"], row["epoch"], row["head_hash"]))
            present = port.present()
            retired = ProtectedSourceRetirement(self._store.restrictions).present()
            if not present and not retired and (row is None or row["transfer_id"] is None):
                return
            if not source_operation_permitted(self._store, binding, action, proposal_id):
                raise CommandRejected()
            fence = port.read() if present else None
            if fence is not None and (fence.workspace_id != binding["workspace_id"] or fence.owner_id != binding["actor_id"]):
                raise CommandRejected()
            if action not in ("command.preview", "conversation.transfer.proof"):
                proposal = self.proposal(binding["workspace_id"], proposal_id)
                if (not proposal or proposal["actor_id"] != binding["actor_id"]
                        or proposal["payload"].get("command") not in ("conversation.transfer.seal", "conversation.transfer.retire")
                        or row is not None and row["transfer_id"] is not None
                           and proposal["payload"].get("attempt_id") != str(row["transfer_id"])
                        or fence is not None and proposal["payload"].get("attempt_id") != str(fence.command.attempt_id)
                        or fence is not None and proposal["payload"].get("command") == "conversation.transfer.seal"
                           and proposal["payload"] != fence.command.canonical()):
                    raise CommandRejected()
        except (TransferUnavailable, RestrictionUnavailable, RetirementUnavailable):
            raise CommandRejected() from None

    def _anchor(self, binding):
        row = self._connection.execute(text("""SELECT authority_id,epoch,head_hash,updated_at
            FROM class_os.conversation_control WHERE workspace_id=:workspace_id AND owner_id=:actor_id"""), binding).mappings().one_or_none()
        if row is None or self._store.restrictions.workspace_id != binding["workspace_id"]:
            raise CommandRejected()
        return row, RestrictionHead(row["authority_id"], binding["workspace_id"], row["epoch"], row["head_hash"])

    def _thread(self, binding, class_id, term_id, thread_id):
        if not self.class_context(binding["workspace_id"], class_id, term_id):
            raise CommandRejected()
        row = self._connection.execute(text("""SELECT title,status,version,updated_at,cleared_at FROM class_os.conversation_thread
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND class_id=:c AND term_id=:t AND thread_id=:thread"""),
            {**binding, "c": class_id, "t": term_id, "thread": thread_id}).mappings().one_or_none()
        if row is None:
            raise CommandRejected()
        return row

    def validate_conversation_control(self, binding, command, now):
        control = self._store.restrictions
        if control.workspace_id != binding["workspace_id"]:
            raise CommandRejected()
        try:
            if type(command) is InitializeConversationControl:
                if self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.conversation_control WHERE workspace_id=:w)
                    OR EXISTS(SELECT 1 FROM class_os.conversation_thread WHERE workspace_id=:w)"""),
                    {"w": binding["workspace_id"]}).scalar_one():
                    raise CommandRejected()
                path = control.root / FILE_NAME
                if path.exists() or path.is_symlink():
                    initial = control.read()
                    if initial.head.authority_id != command.authority_id or initial.markers:
                        raise CommandRejected()
                return
            if type(command) is not ClearConversation:
                raise CommandRejected()
            row, head = self._anchor(binding)
            current = self._thread(binding, command.class_id, command.term_id, command.thread_id)
            if (current["status"] == "cleared" or current["version"] != command.expected_version
                    or now < max(current["updated_at"], row["updated_at"])):
                raise CommandRejected()
            if self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.conversation_run
                WHERE workspace_id=:w AND thread_id=:thread AND state IN ('queued','running','cancel_requested')
                AND (version>=2147483647 OR created_at>:now OR started_at>:now OR cancel_requested_at>:now))"""),
                {"w": binding["workspace_id"], "thread": command.thread_id, "now": now}).scalar_one():
                raise CommandRejected()
            compared = control.compare(head)
            if compared.pending is not None:
                pending = compared.pending
                if (pending.thread_id != command.thread_id or pending.version_after != command.expected_version + 1
                        or not max(current["updated_at"], row["updated_at"]) <= pending.restricted_at <= now):
                    raise CommandRejected()
        except RestrictionUnavailable:
            raise CommandRejected() from None

    def apply(self, binding, command, now):
        if type(command) not in (InitializeConversationControl, ClearConversation):
            return super().apply(binding, command, now)
        self.validate_conversation_control(binding, command, now)
        if type(command) is ClearConversation:
            from .target_import_store import validate_import_integrity
            try:
                validate_import_integrity(self._connection)
            except Exception:
                raise CommandRejected() from None
        legacy = self._legacy_result_rows(binding, command.thread_id) if type(command) is ClearConversation else ()
        if legacy:
            # Conservative bound includes the still-visible text plus new
            # digests. Never publish an irreversible marker before this check.
            from .target_import_store import validate_import_integrity
            trial = self._connection.begin_nested()
            try:
                self._write_legacy_result_receipts(binding, command.thread_id, legacy, now)
                validate_import_integrity(self._connection)
            except Exception:
                raise CommandRejected() from None
            finally:
                trial.rollback()
        control = self._store.restrictions
        try:
            if type(command) is InitializeConversationControl:
                path = control.root / FILE_NAME
                head = control.read().head if path.exists() else control.initialize(command.authority_id)
                self._mutate(text("""INSERT INTO class_os.conversation_control
                    (workspace_id,owner_id,authority_id,epoch,head_hash,created_at,updated_at)
                    VALUES(:workspace_id,:actor_id,:authority,0,:hash,:now,:now)"""),
                    {**binding, "authority": head.authority_id, "hash": head.digest, "now": now})
                return Receipt(uuid4(), head.authority_id, 1)
            _, previous = self._anchor(binding)
            compared = control.compare(previous)
            marker = compared.pending or ClearMarker(command.thread_id, command.expected_version + 1, now)
            head = compared.snapshot.head if compared.pending else control.advance(previous, marker)
        except RestrictionUnavailable:
            raise CommandRejected() from None
        values = {**binding, "thread": command.thread_id, "version": command.expected_version,
                  "at": marker.restricted_at, "hash": head.digest, "epoch": head.epoch,
                  "previous": previous.digest, "previous_epoch": previous.epoch}
        # The external restriction is already durable. Any failure below must
        # roll back SQL/audit/receipt, but MUST NOT roll back the external marker.
        self._write_legacy_result_receipts(binding, command.thread_id, legacy, now)
        self._mutate(text("""UPDATE class_os.conversation_thread SET status='cleared',title='已清除的会话',
            version=version+1,updated_at=:at,cleared_at=:at
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread AND version=:version"""), values)
        count = self._connection.execute(text("""SELECT count(*) FROM class_os.conversation_message
            WHERE workspace_id=:workspace_id AND thread_id=:thread"""), values).scalar_one()
        self._mutate(text("""UPDATE class_os.conversation_message SET body=NULL,visibility='restricted'
            WHERE workspace_id=:workspace_id AND thread_id=:thread"""), values, expected=count)
        drafts = self._connection.execute(text("SELECT count(*) FROM class_os.conversation_task_draft WHERE workspace_id=:workspace_id AND thread_id=:thread"), values).scalar_one()
        self._mutate(text("UPDATE class_os.conversation_task_draft SET title=NULL,visibility='restricted' WHERE workspace_id=:workspace_id AND thread_id=:thread"), values, expected=drafts)
        active = self._connection.execute(text("""SELECT count(*) FROM class_os.conversation_run
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND state IN ('queued','running','cancel_requested')"""), values).scalar_one()
        self._mutate(text("""UPDATE class_os.conversation_run SET version=version+1,ended_at=:at,
            state=CASE WHEN state='queued' THEN 'cancelled' WHEN lease_until<=:at THEN 'interrupted' ELSE 'unknown' END
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND state IN ('queued','running','cancel_requested')"""), values, expected=active)
        self._mutate(text("""UPDATE class_os.conversation_control SET epoch=:epoch,head_hash=:hash,updated_at=:at
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND epoch=:previous_epoch AND head_hash=:previous"""), values)
        return Receipt(uuid4(), command.thread_id, command.expected_version + 1)

    def _legacy_result_rows(self, binding, thread_id):
        rows = self._connection.execute(text("""SELECT m.turn_id,m.message_id,m.body,m.created_at
            FROM class_os.conversation_message m JOIN class_os.conversation_run r USING(workspace_id,thread_id,turn_id)
            WHERE m.workspace_id=:workspace_id AND m.thread_id=:thread AND m.role='assistant'
            AND m.visibility='visible' AND r.state='completed' AND NOT EXISTS(
                SELECT 1 FROM class_os.conversation_result_receipt h WHERE h.workspace_id=m.workspace_id AND h.message_id=m.message_id)
            LIMIT 10001"""), {**binding, "thread": thread_id}).mappings().all()
        if len(rows) > 10000:
            raise CommandRejected()
        if rows:
            # Internal integrity-only projection, also usable during a file-first
            # clear retry. It grants no read/activation or missing witness bypass.
            from .target_import_store import validate_import_integrity
            try:
                validate_import_integrity(self._connection)
            except Exception:
                raise CommandRejected() from None
        return rows

    def _write_legacy_result_receipts(self, binding, thread_id, rows, now):
        for row in rows:
            self._mutate(text("""INSERT INTO class_os.conversation_result_receipt
                (workspace_id,thread_id,turn_id,message_id,message_role,protocol,text_hash,result_hash,created_at,recorded_at)
                VALUES(:workspace_id,:thread,:turn,:message,'assistant','legacy-plain',:digest,:digest,:created,:recorded)"""),
                {**binding, "thread": thread_id, "turn": row["turn_id"], "message": row["message_id"],
                 "digest": checksum(row["body"]), "created": row["created_at"], "recorded": now})

    def conversation_history(self, binding, class_id, term_id, thread_id):
        from .recovery_admission_store import AdmissionTransaction
        if type(self) is not AdmissionTransaction and self._connection.execute(text("""SELECT
            EXISTS(SELECT 1 FROM class_os.conversation_result_receipt
                WHERE workspace_id=:workspace_id AND thread_id=:thread AND protocol='fixed-result')
            OR EXISTS(SELECT 1 FROM class_os.conversation_query_source WHERE workspace_id=:workspace_id AND thread_id=:thread)
            OR EXISTS(SELECT 1 FROM class_os.conversation_task_draft WHERE workspace_id=:workspace_id AND thread_id=:thread)
            OR EXISTS(SELECT 1 FROM class_os.command_proposal WHERE workspace_id=:workspace_id
                AND command_type='conversation.run.finish-result' AND state='committed' AND payload->>'thread_id'=:thread_text)
            OR EXISTS(SELECT 1 FROM class_os.conversation_run r JOIN class_os.business_audit a
                ON a.workspace_id=r.workspace_id AND a.resource_id=r.run_id
                WHERE r.workspace_id=:workspace_id AND r.thread_id=:thread AND r.state='completed'
                AND a.action='command.commit' AND a.outcome='allowed' AND a.purpose='manage-conversation')"""),
                {**binding, "thread": thread_id, "thread_text": str(thread_id)}).scalar_one():
            raise CommandRejected()  # An old body reader cannot strip typed evidence.
        try:
            _, head = self._anchor(binding)
            compared = self._store.restrictions.compare(head)
            if compared.state != "aligned":
                raise CommandRejected()
            current = self._thread(binding, class_id, term_id, thread_id)
            marker = next((item for item in compared.snapshot.markers if item.thread_id == thread_id), None)
            if ((current["status"] == "cleared") != (marker is not None)
                    or marker is not None and (current["version"] != marker.version_after
                                                or current["cleared_at"] != marker.restricted_at)):
                raise CommandRejected()
            messages, truncated = (), False
            if current["status"] != "cleared":
                turns = self._connection.execute(text("""SELECT turn_id FROM class_os.conversation_turn
                    WHERE workspace_id=:w AND thread_id=:thread ORDER BY ordinal DESC LIMIT 51"""),
                    {"w": binding["workspace_id"], "thread": thread_id}).scalars().all()
                truncated = len(turns) > 50
                rows = self._connection.execute(text("""SELECT m.message_id,m.turn_id,m.role,m.origin,m.body,m.visibility,m.created_at
                    FROM class_os.conversation_message m JOIN class_os.conversation_turn t USING(workspace_id,thread_id,turn_id)
                    WHERE m.workspace_id=:w AND m.thread_id=:thread AND m.turn_id=ANY(CAST(:turns AS uuid[]))
                    ORDER BY t.ordinal,CASE m.role WHEN 'user' THEN 0 ELSE 1 END LIMIT 101"""),
                    {"w": binding["workspace_id"], "thread": thread_id, "turns": list(turns[:50])}).mappings().all()
                if len(rows) > 100 or any(row["visibility"] != "visible" for row in rows):
                    raise CommandRejected()
                messages = tuple(HistoryMessage(row["message_id"], row["turn_id"], row["created_at"],
                                               VisibleMessage(row["role"], row["origin"], row["body"])) for row in rows)
            return ConversationHistory(thread_id, current["title"], current["status"], current["version"], messages, truncated)
        except RestrictionUnavailable:
            raise CommandRejected() from None
