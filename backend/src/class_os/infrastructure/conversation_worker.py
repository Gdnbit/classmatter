"""Fixed server-owned run CAS, mixed into the existing BCG transaction."""
from uuid import UUID, uuid4
import json

from sqlalchemy import text

from class_os.application.roster import CommandRejected, fingerprint
from class_os.domain.conversation_worker import ClaimRun, FinishRun, CancelRun, ReconcileRun
from class_os.domain.conversation_results import FinishResult, ProducedResult
from class_os.domain.conversation_interaction import EnqueueConversation
from class_os.domain.durable_conversation import ConversationRun, ConversationScope, SendIntent, VisibleMessage
from class_os.domain.exit_package import checksum
from class_os.domain.roster import Receipt


def run_value(row):
    try:
        return ConversationRun(**{key: row[key] for key in ("run_id", "state", "version", "generation", "started_at",
            "lease_until", "ended_at", "cancel_requested_at")})
    except ValueError:
        raise CommandRejected() from None


def verify_native_result_commits(connection, binding, conversations):
    """Use original SQL proposals/receipts, never sidecar absence, to classify output."""
    from class_os.domain.conversation_exit_v6 import finish_command
    from class_os.domain.conversation_result_integrity import message_key
    threads = {row["thread_id"]: row for row in conversations["conversation_thread"]}
    for run in conversations["conversation_run"]:
        if run["state"] != "completed":
            continue
        messages = [row for row in conversations["conversation_message"] if row["thread_id"] == run["thread_id"]
                    and row["turn_id"] == run["turn_id"] and row["role"] == "assistant"]
        if len(messages) != 1:
            continue
        message, thread = messages[0], threads[run["thread_id"]]
        # Imported messages have no local completion proposal; the caller supplies
        # only native messages below. A missing local proposal is never legacy.
        commands = connection.execute(text("""SELECT p.command_type FROM class_os.command_proposal p
            JOIN class_os.command_receipt r ON r.proposal_id=p.proposal_id AND r.workspace_id=p.workspace_id
            WHERE p.workspace_id=:workspace_id AND p.actor_id=:actor_id AND p.state='committed'
            AND r.actor_id=p.actor_id AND r.resource_id=:run AND r.resource_version=:version
            AND p.command_type IN ('conversation.run.finish','conversation.run.finish-result')"""),
            {**binding, "run": UUID(run["run_id"]), "version": run["version"]}).scalars().all()
        if len(commands) != 1:
            raise ValueError("Missing original native result classification")
        group = {"sources": sorted((row for row in conversations["conversation_query_source"] if message_key(row) == message_key(message)), key=lambda row: row["ordinal"]),
                 "draft": next((row for row in conversations["conversation_task_draft"] if message_key(row) == message_key(message)), None)}
        header = next((row for row in conversations["conversation_result_receipt"] if message_key(row) == message_key(message)), None)
        if commands[0] == FinishResult.command:
            if header is None or header["protocol"] != "fixed-result":
                raise ValueError("Missing original result receipt")
            payload = finish_command(thread, run, result_hash=header["result_hash"]).canonical()
        else:
            if group["sources"] or group["draft"] is not None or header is not None and header["protocol"] != "legacy-plain":
                raise ValueError("Legacy output cannot acquire typed metadata")
            if message["visibility"] != "visible" and header is None:
                raise ValueError("Missing cleared legacy digest")
            payload = finish_command(thread, run, legacy_hash=header["text_hash"]).canonical() if header is not None else finish_command(thread, run, legacy_body=message["body"]).canonical()
        valid = connection.execute(text("""SELECT count(*) FROM class_os.command_proposal p
            JOIN class_os.command_receipt r ON r.proposal_id=p.proposal_id AND r.workspace_id=p.workspace_id
            JOIN class_os.business_audit a ON a.receipt_id=r.receipt_id AND a.workspace_id=r.workspace_id
            WHERE p.workspace_id=:workspace_id AND p.actor_id=:actor_id AND p.state='committed'
            AND r.actor_id=p.actor_id AND r.resource_id=:run AND r.resource_version=:version
            AND p.purpose='manage-conversation' AND p.payload=CAST(:payload AS jsonb) AND p.payload_hash=:hash
            AND r.payload_hash=:hash AND r.committed_at=:ended AND a.proposal_id=p.proposal_id
            AND a.actor_id=p.actor_id AND a.action='command.commit' AND a.outcome='allowed'
            AND a.purpose=p.purpose AND a.payload_hash=:hash AND a.resource_id=r.resource_id
            AND a.resource_version=r.resource_version AND a.occurred_at=r.committed_at
            AND a.class_id=:class AND a.term_id=:term"""),
            {**binding, "run": UUID(run["run_id"]), "version": run["version"], "payload": json.dumps(payload),
             "hash": fingerprint(payload), "ended": run["ended_at"], "class": UUID(thread["class_id"]), "term": UUID(thread["term_id"])}).scalar_one()
        if valid != 1:
            raise ValueError("Missing complete original native result commit")


class WorkerTransaction:
    def require_worker_claim(self, binding, ticket, class_id, term_id, thread_id):
        command = ClaimRun(thread_id, class_id, term_id, ticket.run.run_id, 1,
                           ticket.run.generation, ticket.run.lease_until, ticket.intent.request_hash)
        payload = command.canonical()
        committed = self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.command_receipt r
            JOIN class_os.command_proposal p ON p.proposal_id=r.proposal_id
            JOIN class_os.business_audit a ON a.receipt_id=r.receipt_id AND a.workspace_id=r.workspace_id
            WHERE r.workspace_id=:workspace_id AND r.actor_id=:actor_id AND r.resource_id=:run
            AND r.resource_version=2 AND r.payload_hash=:hash AND r.committed_at=:started
            AND p.workspace_id=r.workspace_id AND p.actor_id=r.actor_id AND p.state='committed'
            AND p.command_type='conversation.run.claim' AND p.purpose='manage-conversation'
            AND p.payload_hash=:hash AND p.payload=CAST(:payload AS jsonb)
            AND a.actor_id=r.actor_id AND a.action='command.commit' AND a.outcome='allowed'
            AND a.purpose=p.purpose AND a.proposal_id=p.proposal_id AND a.payload_hash=:hash
            AND a.resource_id=r.resource_id AND a.resource_version=2 AND a.occurred_at=r.committed_at)"""),
            {**binding, "run": ticket.run.run_id, "hash": fingerprint(payload), "started": ticket.run.started_at,
             "payload": json.dumps(payload)}).scalar_one()
        if not committed:
            raise CommandRejected()

    def worker_row(self, binding, class_id, term_id, thread_id, now, *, run_id=None, request_id=None, active=True):
        thread = self.interaction_thread(binding, class_id, term_id, thread_id, now, active=active)
        if (run_id is None) == (request_id is None) or type(run_id if run_id is not None else request_id) is not UUID:
            raise CommandRejected()
        predicate = "r.run_id=:key" if run_id is not None else "t.client_request_id=:key"
        row = self._connection.execute(text("""SELECT r.run_id,r.turn_id,r.state,r.version,r.generation,r.created_at,
            r.queued_until,r.started_at,r.lease_until,r.ended_at,r.cancel_requested_at,
            t.client_request_id,t.request_hash,t.mode,t.draft_kind,m.body,m.origin,m.visibility
            FROM class_os.conversation_run r JOIN class_os.conversation_turn t USING(workspace_id,thread_id,turn_id)
            LEFT JOIN class_os.conversation_message m ON m.workspace_id=r.workspace_id AND m.thread_id=r.thread_id
                AND m.turn_id=r.turn_id AND m.role='user'
            WHERE r.workspace_id=:workspace_id AND r.thread_id=:thread AND """ + predicate),
            {**binding, "thread": thread_id, "key": run_id if run_id is not None else request_id}).mappings().one_or_none()
        if row is None or now < row["created_at"] or thread["version"] >= 2147483647:
            raise CommandRejected()
        run_value(row)
        return {**row, "student_id": thread["student_id"], "thread_version": thread["version"]}

    def worker_input(self, binding, class_id, term_id, thread_id, row):
        from class_os.application.conversation_interaction import send_receipt_key
        if row["origin"] != "user-original" or row["visibility"] != "visible":
            raise CommandRejected()
        try:
            scope = ConversationScope(binding["workspace_id"], binding["actor_id"], class_id, term_id, row["student_id"])
            intent = SendIntent(scope, thread_id, row["client_request_id"], row["body"], row["mode"], row["draft_kind"])
            command = EnqueueConversation.from_intent(intent)
        except ValueError:
            raise CommandRejected() from None
        if intent.request_hash != row["request_hash"]:
            raise CommandRejected()
        receipt = self.interaction_replay(binding, command, send_receipt_key(scope, thread_id, intent.client_request_id), intent)
        if receipt is None or receipt.receipt.resource_id != row["run_id"]:
            raise CommandRejected()
        return intent

    def validate_worker(self, binding, command, now):
        from class_os.application.conversation_worker import current_worker_operation
        ticket, output = current_worker_operation(self._store, binding, command)
        active = type(command) in (ClaimRun, FinishRun, FinishResult)
        row = self.worker_row(binding, command.class_id, command.term_id, command.thread_id, now, run_id=command.run_id, active=active)
        current = run_value(row)
        try:
            if type(command) is ClaimRun:
                intent = self.worker_input(binding, command.class_id, command.term_id, command.thread_id, row)
                if (row["version"] != 1 or not now < row["queued_until"] or command.request_hash != intent.request_hash):
                    raise CommandRejected()
                return row, current.start(command.expected_version, command.generation, now, command.lease_until), None
            if type(command) in (FinishRun, FinishResult):
                if (ticket is None or ticket.scope.workspace_id != binding["workspace_id"] or ticket.scope.owner_id != binding["actor_id"]
                        or ticket.intent.thread_id != command.thread_id or ticket.run.run_id != command.run_id
                        or ticket.scope.class_id != command.class_id or ticket.scope.term_id != command.term_id
                        or ticket.turn_id != row["turn_id"] or ticket.run.generation != command.generation
                        or current.generation != ticket.run.generation or current.started_at != ticket.run.started_at
                        or current.lease_until != ticket.run.lease_until
                        or not (current.version == ticket.run.version or current.state == "cancel_requested" and current.version == ticket.run.version + 1)):
                    raise CommandRejected()
                actual = self.worker_input(binding, command.class_id, command.term_id, command.thread_id, row)
                if actual != ticket.intent:
                    raise CommandRejected()
                self.require_worker_claim(binding, ticket, command.class_id, command.term_id, command.thread_id)
                if type(command) is FinishResult:
                    if type(output) is not ProducedResult or output.result_hash != command.result_hash:
                        raise CommandRejected()
                    output.validate_intent(actual)
                    self.require_result_sources(binding, ticket, output, now)
                elif command.state == "completed":
                    VisibleMessage("assistant", "assistant-unverified", output)
                    if len(output) > 4000 or checksum(output) != command.output_hash:
                        raise CommandRejected()
                elif output is not None:
                    raise CommandRejected()
                return row, current.finish(command.expected_version, command.generation, command.state, now), output
            if type(command) is CancelRun:
                return row, current.request_cancel(command.expected_version, now), None
            if type(command) is ReconcileRun:
                if current.state == "queued":
                    if now < row["queued_until"]:
                        raise CommandRejected()
                    return row, current.request_cancel(command.expected_version, now), None
                return row, current.expire(command.expected_version, now), None
        except ValueError:
            raise CommandRejected() from None
        raise CommandRejected()

    def require_result_sources(self, binding, ticket, result, now):
        for source in result.sources:
            if not ticket.run.started_at <= source.as_of <= now < ticket.run.lease_until:
                raise CommandRejected()
            valid = self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.business_audit
                WHERE workspace_id=:workspace_id AND actor_id=:actor_id AND event_id=:receipt
                AND action='activity.today' AND outcome='allowed' AND purpose='manage-class'
                AND class_id=:class AND term_id=:term AND resource_id=:resource
                AND resource_version>0 AND payload_hash=:hash AND occurred_at=:as_of)"""),
                {**binding, "receipt": source.receipt_id, "class": ticket.scope.class_id, "term": ticket.scope.term_id,
                 "resource": ticket.scope.student_id or ticket.scope.class_id, "hash": source.projection_hash, "as_of": source.as_of}).scalar_one()
            if not valid:
                raise CommandRejected()

    def apply_worker(self, binding, command, now):
        row, changed, output = self.validate_worker(binding, command, now)
        values = {**binding, "thread": command.thread_id, "run": command.run_id, "version": command.expected_version,
            "prior_generation": row["generation"], "state": changed.state, "after": changed.version,
            "generation": changed.generation, "started": changed.started_at, "lease": changed.lease_until,
            "ended": changed.ended_at, "cancelled": changed.cancel_requested_at, "now": now,
            "duration": command.duration_ms if type(command) in (FinishRun, FinishResult) else None,
            "input": command.input_tokens if type(command) in (FinishRun, FinishResult) else None,
            "output": command.output_tokens if type(command) in (FinishRun, FinishResult) else None}
        self._mutate(text("""UPDATE class_os.conversation_run SET state=:state,version=:after,generation=:generation,
            started_at=:started,lease_until=:lease,ended_at=:ended,cancel_requested_at=:cancelled,
            duration_ms=:duration,input_tokens=:input,output_tokens=:output
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND run_id=:run AND version=:version
            AND generation IS NOT DISTINCT FROM CAST(:prior_generation AS uuid)"""), values)
        if output is not None:
            message = uuid4()
            self._mutate(text("""INSERT INTO class_os.conversation_message
                (workspace_id,thread_id,turn_id,message_id,role,origin,visibility,body,created_at)
                VALUES(:workspace_id,:thread,:turn,:message,'assistant','assistant-unverified','visible',:body,:now)"""),
                {**values, "turn": row["turn_id"], "message": message,
                 "body": output.text if type(output) is ProducedResult else output})
            parent = {**values, "turn": row["turn_id"], "message": message}
            typed = type(output) is ProducedResult
            self._mutate(text("""INSERT INTO class_os.conversation_result_receipt
                (workspace_id,thread_id,turn_id,message_id,message_role,protocol,text_hash,result_hash,created_at,recorded_at)
                VALUES(:workspace_id,:thread,:turn,:message,'assistant',:protocol,:text_hash,:result_hash,:now,:now)"""),
                {**parent, "protocol": "fixed-result" if typed else "legacy-plain",
                 "text_hash": checksum(output.text if typed else output), "result_hash": output.result_hash if typed else checksum(output)})
            if typed:
                for ordinal, source in enumerate(output.sources, 1):
                    self._mutate(text("""INSERT INTO class_os.conversation_query_source
                        (workspace_id,thread_id,turn_id,message_id,message_role,source_id,ordinal,
                         source_workspace_id,source_owner_id,receipt_id,projection_hash,as_of,created_at)
                        VALUES(:workspace_id,:thread,:turn,:message,'assistant',:source_id,:ordinal,
                               :source_workspace_id,:source_owner_id,:receipt_id,:projection_hash,:as_of,:now)"""),
                        {**parent, **{key: getattr(source, key) for key in ("source_id", "source_workspace_id", "source_owner_id", "receipt_id", "projection_hash", "as_of")}, "ordinal": ordinal})
                if output.draft is not None:
                    draft = output.draft
                    self._mutate(text("""INSERT INTO class_os.conversation_task_draft
                        (workspace_id,thread_id,turn_id,message_id,message_role,draft_id,title,title_hash,visibility,created_at)
                        VALUES(:workspace_id,:thread,:turn,:message,'assistant',:draft,:title,:hash,'visible',:now)"""),
                        {**parent, "draft": draft.task_id, "title": draft.title, "hash": checksum(draft.title)})
        self._mutate(text("""UPDATE class_os.conversation_thread SET version=version+1,updated_at=:now
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND version=:thread_version"""),
            {**values, "thread_version": row["thread_version"]})
        return Receipt(uuid4(), command.run_id, changed.version)
