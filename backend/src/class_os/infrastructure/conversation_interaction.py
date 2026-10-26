"""Fixed interaction SQL mixed into the existing attributed BCG transaction."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text

from class_os.application.roster import CommandRejected, fingerprint
from class_os.domain.conversation_interaction import CreateConversation, RenameConversation, ArchiveConversation, EnqueueConversation
from class_os.domain.roster import Receipt, CommandStatus


@dataclass(frozen=True)
class ConversationPage:
    items: tuple[dict, ...]
    truncated: bool


@dataclass(frozen=True)
class ConversationListing:
    items: tuple[dict, ...]
    snapshot: str
    next_offset: int | None


class InteractionTransaction:
    def interaction_context(self, binding, class_id, term_id, *, active=True):
        from .target_import import ProtectedTargetImport, ImportUnavailable
        from .recovery_admission import ProtectedTargetAdmission, AdmissionUnavailable
        admitted = self.has_committed_admission(binding)
        try:
            if not admitted and (ProtectedTargetImport(self._store.restrictions).present()
                                 or ProtectedTargetAdmission(self._store.restrictions).present()):
                raise CommandRejected()
        except (ImportUnavailable, AdmissionUnavailable):
            raise CommandRejected() from None
        if type(class_id) is not UUID or type(term_id) is not UUID:
            raise CommandRejected()
        context = self.class_context(binding["workspace_id"], class_id, term_id)
        if not context or active and (context["status"] != "active" or context["term_status"] != "active"):
            raise CommandRejected()
        current = self.current_context(binding["workspace_id"])
        if active and (current is None or current.class_id != class_id or current.term_id != term_id):
            raise CommandRejected()
        if self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.conversation_import i
            WHERE i.workspace_id=:workspace_id AND NOT EXISTS(SELECT 1 FROM class_os.conversation_admission a
                WHERE a.workspace_id=i.workspace_id))"""), binding).scalar_one():
            raise CommandRejected()
        self._proof(binding)

    def interaction_thread(self, binding, class_id, term_id, thread_id, now, *, active=True):
        self.interaction_context(binding, class_id, term_id, active=active)
        if type(thread_id) is not UUID:
            raise CommandRejected()
        row = self._connection.execute(text("""SELECT thread_id,student_id,enrollment_id,title,status,version,created_at,updated_at
            FROM class_os.conversation_thread WHERE workspace_id=:workspace_id AND owner_id=:actor_id
            AND class_id=:c AND term_id=:t AND thread_id=:thread"""),
            {**binding, "c": class_id, "t": term_id, "thread": thread_id}).mappings().one_or_none()
        if row is None or now < row["updated_at"] or active and row["status"] != "active":
            raise CommandRejected()
        if active and row["student_id"] is not None:
            eligible = self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.enrollment e
                JOIN class_os.student s USING(workspace_id,student_id) WHERE e.workspace_id=:workspace_id
                AND e.enrollment_id=:e AND e.class_id=:c AND e.term_id=:t AND e.student_id=:s
                AND e.status='active' AND s.status='active' AND e.valid_from<=:now AND (e.valid_to IS NULL OR :now<e.valid_to))"""),
                {**binding, "e": row["enrollment_id"], "s": row["student_id"], "c": class_id, "t": term_id, "now": now}).scalar_one()
            if not eligible:
                raise CommandRejected()
        return row

    def validate_interaction(self, binding, command, now):
        if type(command) in (CreateConversation, RenameConversation):
            from class_os.application.conversation_interaction import current_human_title
            current_human_title(self._store, binding, command)
        if type(command) is CreateConversation:
            self.interaction_context(binding, command.class_id, command.term_id)
            if self._connection.execute(text("SELECT EXISTS(SELECT 1 FROM class_os.conversation_thread WHERE workspace_id=:workspace_id AND thread_id=:thread)"),
                                        {**binding, "thread": command.thread_id}).scalar_one():
                raise CommandRejected()
            if command.student_id is not None and not self.active_student(binding["workspace_id"], command.class_id, command.term_id, command.student_id, now):
                raise CommandRejected()
            return
        if type(command) not in (RenameConversation, ArchiveConversation, EnqueueConversation):
            raise CommandRejected()
        row = self.interaction_thread(binding, command.class_id, command.term_id, command.thread_id, now)
        if row["version"] >= 2147483647:
            raise CommandRejected()
        if type(command) is EnqueueConversation:
            from class_os.application.conversation_interaction import current_send_input
            intent = current_send_input(self._store, binding, command)
            if row["student_id"] != intent.scope.student_id or intent.scope.owner_id != binding["actor_id"] or intent.scope.workspace_id != binding["workspace_id"]:
                raise CommandRejected()
        elif row["version"] != command.expected_version:
            raise CommandRejected()
        if type(command) in (ArchiveConversation, EnqueueConversation) and self._connection.execute(text("""SELECT EXISTS(
            SELECT 1 FROM class_os.conversation_run WHERE workspace_id=:workspace_id AND thread_id=:thread
            AND state IN ('queued','running','cancel_requested'))"""), {**binding, "thread": command.thread_id}).scalar_one():
            raise CommandRejected()

    def apply_interaction(self, binding, command, now):
        from class_os.application.conversation_interaction import current_human_title
        self.validate_interaction(binding, command, now)
        values = {**binding, "thread": command.thread_id, "c": command.class_id, "t": command.term_id, "now": now}
        if type(command) is CreateConversation:
            enrollment = None
            if command.student_id is not None:
                enrollment = self._connection.execute(text("""SELECT enrollment_id FROM class_os.enrollment
                    WHERE workspace_id=:workspace_id AND student_id=:s AND class_id=:c AND term_id=:t
                    AND status='active' AND valid_from<=:now AND (valid_to IS NULL OR :now<valid_to)"""),
                    {**values, "s": command.student_id}).scalar_one()
            self._mutate(text("""INSERT INTO class_os.conversation_thread
                (workspace_id,thread_id,owner_id,class_id,term_id,student_id,enrollment_id,title,status,version,created_at,updated_at)
                VALUES(:workspace_id,:thread,:actor_id,:c,:t,:s,:e,:title,'active',1,:now,:now)"""),
                {**values, "s": command.student_id, "e": enrollment,
                 "title": current_human_title(self._store, binding, command)})
            return Receipt(uuid4(), command.thread_id, 1)
        if type(command) is EnqueueConversation:
            from class_os.application.conversation_interaction import current_send_input
            intent = current_send_input(self._store, binding, command)
            ordinal = self._connection.execute(text("SELECT coalesce(max(ordinal),0)+1 FROM class_os.conversation_turn WHERE workspace_id=:workspace_id AND thread_id=:thread"), values).scalar_one()
            if ordinal > 10000:
                raise CommandRejected()
            turn, run = uuid4(), uuid4()
            values.update(turn=turn, run=run, ordinal=ordinal, key=command.client_request_id, hash=command.request_hash,
                          mode=command.mode, draft=command.draft_kind, body=intent.text, message=uuid4(), until=now + timedelta(minutes=1))
            self._mutate(text("""INSERT INTO class_os.conversation_turn
                (workspace_id,thread_id,turn_id,ordinal,client_request_id,request_hash,mode,draft_kind,created_at)
                VALUES(:workspace_id,:thread,:turn,:ordinal,:key,:hash,:mode,:draft,:now)"""), values)
            self._mutate(text("""INSERT INTO class_os.conversation_message
                (workspace_id,thread_id,turn_id,message_id,role,origin,visibility,body,created_at)
                VALUES(:workspace_id,:thread,:turn,:message,'user','user-original','visible',:body,:now)"""), values)
            self._mutate(text("""INSERT INTO class_os.conversation_run
                (workspace_id,thread_id,turn_id,run_id,state,version,created_at,queued_until)
                VALUES(:workspace_id,:thread,:turn,:run,'queued',1,:now,:until)"""), values)
            self._mutate(text("UPDATE class_os.conversation_thread SET version=version+1,updated_at=:now WHERE workspace_id=:workspace_id AND thread_id=:thread"), values)
            return Receipt(uuid4(), run, 1)
        self._mutate(text("""UPDATE class_os.conversation_thread SET title=:title,status=:status,version=version+1,updated_at=:now
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND version=:version"""),
            {**values, "version": command.expected_version, "title": current_human_title(self._store, binding, command) if type(command) is RenameConversation else self._thread(binding, command.class_id, command.term_id, command.thread_id)["title"],
             "status": "archived" if type(command) is ArchiveConversation else "active"})
        return Receipt(uuid4(), command.thread_id, command.expected_version + 1)

    def interaction_replay(self, binding, command, key, intent):
        if not command.matches(intent):
            raise CommandRejected()
        receipt = self.receipt(binding, key)
        turn = self._connection.execute(text("""SELECT t.request_hash,t.mode,t.draft_kind,r.run_id,m.body,m.origin,m.visibility
            FROM class_os.conversation_turn t
            JOIN class_os.conversation_run r USING(workspace_id,thread_id,turn_id)
            LEFT JOIN class_os.conversation_message m ON m.workspace_id=t.workspace_id AND m.thread_id=t.thread_id
                AND m.turn_id=t.turn_id AND m.role='user'
            WHERE t.workspace_id=:workspace_id AND t.thread_id=:thread AND t.client_request_id=:key"""),
            {**binding, "thread": command.thread_id, "key": command.client_request_id}).mappings().one_or_none()
        if receipt is None and turn is None:
            return None
        proposal = self.proposal(binding["workspace_id"], receipt["proposal_id"]) if receipt else None
        expected = fingerprint(command.canonical())
        receipt_hash = self._connection.execute(text("SELECT payload_hash FROM class_os.command_receipt WHERE workspace_id=:workspace_id AND actor_id=:actor_id AND idempotency_key=:key"),
                                                {**binding, "key": key}).scalar_one_or_none()
        if (receipt is None or turn is None or proposal is None or turn["request_hash"] != command.request_hash
                or turn["mode"] != command.mode or turn["draft_kind"] != command.draft_kind
                or turn["body"] != intent.text or turn["origin"] != "user-original" or turn["visibility"] != "visible"
                or receipt["receipt"].resource_id != turn["run_id"] or proposal["actor_id"] != binding["actor_id"]
                or proposal["state"] != "committed" or proposal["payload"] != command.canonical()
                or proposal["payload_hash"] != expected or receipt_hash != expected):
            raise CommandRejected()
        self.require_interaction_commit(binding, key, expected, command)
        return CommandStatus(receipt["proposal_id"], expected, "committed", receipt["receipt"])

    def require_interaction_commit(self, binding, key, expected, command):
        if type(command) not in (CreateConversation, RenameConversation, ArchiveConversation, EnqueueConversation):
            raise CommandRejected()
        version = command.expected_version + 1 if type(command) in (RenameConversation, ArchiveConversation) else 1
        committed = self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.business_audit a
            JOIN class_os.command_receipt r ON r.receipt_id=a.receipt_id AND r.workspace_id=a.workspace_id
            JOIN class_os.command_proposal p ON p.proposal_id=r.proposal_id
            WHERE r.workspace_id=:workspace_id AND r.actor_id=:actor_id AND r.idempotency_key=:key AND r.payload_hash=:hash
            AND r.resource_version=:version AND p.workspace_id=r.workspace_id AND p.actor_id=r.actor_id
            AND p.command_type=:command AND p.payload_hash=:hash AND p.purpose='manage-conversation' AND p.state='committed'
            AND a.actor_id=r.actor_id AND a.action='command.commit' AND a.outcome='allowed'
            AND a.purpose='manage-conversation' AND a.proposal_id=r.proposal_id AND a.payload_hash=:hash
            AND a.resource_id=r.resource_id AND a.resource_version=r.resource_version AND a.occurred_at=r.committed_at)"""),
            {**binding, "key": key, "hash": expected, "version": version, "command": command.command}).scalar_one()
        if not committed:
            raise CommandRejected()

    def interaction_list(self, binding, class_id, term_id, now):
        self.interaction_context(binding, class_id, term_id, active=False)
        rows = self._connection.execute(text("""SELECT thread_id,title,status,version,student_id,updated_at FROM class_os.conversation_thread
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND class_id=:c AND term_id=:t
            ORDER BY updated_at DESC,thread_id LIMIT 51"""), {**binding, "c": class_id, "t": term_id}).mappings().all()
        _, snapshot = self._attribution_snapshot(binding["workspace_id"], now)
        return ConversationPage(tuple({**row, "attribution": self._attribution(snapshot, binding["actor_id"], "conversation_thread", row["thread_id"], row["version"])}
                                      for row in rows[:50]), len(rows) > 50)

    def interaction_list_page(self, binding, class_id, term_id, now, *, snapshot=None, offset=0):
        from class_os.domain.exit_package import checksum
        self.interaction_context(binding, class_id, term_id, active=False)
        if (type(offset) is not int or not 0 <= offset < 10000 or offset % 50
                or snapshot is None and offset != 0
                or snapshot is not None and (type(snapshot) is not str or len(snapshot) != 64
                    or any(char not in "0123456789abcdef" for char in snapshot))):
            raise CommandRejected()
        rows = self._connection.execute(text("""SELECT thread_id,title,status,version,student_id,updated_at FROM class_os.conversation_thread
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND class_id=:c AND term_id=:t
            ORDER BY updated_at DESC,thread_id LIMIT 10001"""), {**binding, "c": class_id, "t": term_id}).mappings().all()
        if len(rows) > 10000:
            raise CommandRejected()
        _, state = self._attribution_snapshot(binding["workspace_id"], now)
        self.verified_result_bundle(binding, now, state)
        items = tuple({**row, "attribution": self._attribution(state, binding["actor_id"], "conversation_thread", row["thread_id"], row["version"])}
                      for row in rows)
        digest = checksum([{key: str(value) if isinstance(value, UUID) else value.isoformat() if isinstance(value, datetime) else value
                            for key, value in row.items()} for row in items])
        if snapshot is not None and snapshot != digest:
            raise CommandRejected()
        return ConversationListing(items[offset:offset + 50], digest, offset + 50 if offset + 50 < len(items) else None)

    def interaction_status(self, binding, class_id, term_id, thread_id, request_id, now):
        self.interaction_thread(binding, class_id, term_id, thread_id, now, active=False)
        if type(request_id) is not UUID:
            raise CommandRejected()
        row = self._connection.execute(text("""SELECT r.run_id,r.state,r.version,r.created_at,r.queued_until,r.ended_at
            FROM class_os.conversation_run r JOIN class_os.conversation_turn t USING(workspace_id,thread_id,turn_id)
            WHERE r.workspace_id=:workspace_id AND r.thread_id=:thread AND t.client_request_id=:key"""),
            {**binding, "thread": thread_id, "key": request_id}).mappings().one_or_none()
        if row is None:
            raise CommandRejected()
        return dict(row)
