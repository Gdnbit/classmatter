"""Fixed D3 chat SQL inside the existing serialized QG/BCG transaction."""
from uuid import UUID, uuid4

from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.roster import identifiers, name
from class_os.domain.workspace_chat import input_hash, message, candidate_hash, validate_turn, ACTIVE, TERMINAL, LEASE, MAX_TURNS
from .workbench import WorkbenchTransaction


class WorkspaceChatTransaction(WorkbenchTransaction):
    def authorize_boundary(self, binding, action, proposal_id):
        if action.startswith("workspace.chat."):
            if proposal_id is not None:
                raise CommandRejected()
            # Same native control, file-first clear and transfer/admission fences.
            return super().authorize_boundary(binding, "class.context", None)
        return super().authorize_boundary(binding, action, proposal_id)

    def audit(self, binding, action, outcome, now, metadata):
        if not action.startswith("workspace.chat."):
            return super().audit(binding, action, outcome, now, metadata)
        event = uuid4()
        return self._connection.execute(text("""INSERT INTO class_os.workspace_chat_audit
            (workspace_id,event_id,owner_id,action,outcome,resource_id,resource_version,occurred_at)
            VALUES(:workspace_id,:event,:actor_id,:action,:outcome,:resource,:version,:now) RETURNING event_id"""),
            {**binding, "event": event, "action": action, "outcome": outcome, "resource": metadata["resource_id"],
             "version": metadata["resource_version"], "now": now}).scalar_one()

    def chat_header(self, binding, thread_id, *, active=False):
        identifiers(thread_id)
        row = self._connection.execute(text("""SELECT thread_id,title,status,version,created_at,updated_at,cleared_at
            FROM class_os.workspace_chat_thread WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread"""),
            {**binding, "thread": thread_id}).mappings().one_or_none()
        if row is None or active and row["status"] != "active":
            raise CommandRejected()
        return dict(row)

    def _chat_turn(self, binding, thread_id, request_id):
        self.chat_header(binding, thread_id)
        identifiers(request_id)
        row = self._connection.execute(text("""SELECT * FROM class_os.workspace_chat_turn
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND request_id=:request"""),
            {**binding, "thread": thread_id, "request": request_id}).mappings().one_or_none()
        if row is None:
            raise CommandRejected()
        return dict(row)

    def chat_list(self, binding, *, offset=0):
        if type(offset) is not int or not 0 <= offset < 10000 or offset % 50:
            raise CommandRejected()
        rows = [dict(row) for row in self._connection.execute(text("""SELECT thread_id,title,status,version,created_at,updated_at,cleared_at
            FROM class_os.workspace_chat_thread WHERE workspace_id=:workspace_id AND owner_id=:actor_id
            ORDER BY updated_at DESC,thread_id DESC LIMIT 51 OFFSET :offset"""), {**binding, "offset": offset}).mappings()]
        return {"data": rows[:50], "next_offset": offset + 50 if len(rows) > 50 else None}

    def chat_history(self, binding, thread_id, *, before=None):
        header = self.chat_header(binding, thread_id)
        if before is not None and (type(before) is not int or not 1 <= before <= MAX_TURNS):
            raise CommandRejected()
        rows = [dict(row) for row in self._connection.execute(text("""SELECT * FROM class_os.workspace_chat_turn
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND (CAST(:before AS integer) IS NULL OR ordinal<:before)
            ORDER BY ordinal DESC LIMIT 21"""), {**binding, "thread": thread_id, "before": before}).mappings()]
        for row in rows:
            validate_turn(row, cleared=header["status"] == "cleared")
            if header["status"] != "cleared" and input_hash(binding["workspace_id"], binding["actor_id"], thread_id, row["user_text"]) != row["input_hash"]:
                raise CommandRejected()
            row["action_receipt"] = self.chat_action_receipt(binding, row)
        import json
        selected, size = [], 0
        for row in rows[:20]:
            added = len(json.dumps(row, default=str, ensure_ascii=False).encode('utf-8'))
            if selected and size + added > 9 * 1024 * 1024:
                break
            selected.append(row); size += added
        visible = list(reversed(selected))
        return {"thread": header, "turns": visible, "next_before": visible[0]["ordinal"] if len(rows) > len(selected) else None}

    def chat_action_receipt(self, binding, row):
        if row["candidate"] is None:
            return None
        import json
        result = self._connection.execute(text("""SELECT r.receipt_id,r.resource_id,r.resource_version AS version
            FROM class_os.command_receipt r JOIN class_os.command_proposal p ON p.workspace_id=r.workspace_id AND p.proposal_id=r.proposal_id
            JOIN class_os.business_audit a ON a.workspace_id=r.workspace_id AND a.receipt_id=r.receipt_id
            WHERE r.workspace_id=:workspace_id AND r.actor_id=:actor_id AND p.actor_id=:actor_id
            AND p.state='committed' AND p.payload_hash=:hash AND r.payload_hash=:hash AND p.payload=CAST(:payload AS jsonb)
            AND a.actor_id=:actor_id AND a.action='command.commit' AND a.outcome='allowed'
            AND a.resource_id=r.resource_id AND a.resource_version=r.resource_version LIMIT 1"""),
            {**binding, "hash": row["candidate_hash"], "payload": json.dumps(row["candidate"], ensure_ascii=False)}).mappings().one_or_none()
        return dict(result) if result else None

    def chat_turn_view(self, binding, thread_id, request_id):
        header = self.chat_header(binding, thread_id)
        row = self._chat_turn(binding, thread_id, request_id)
        validate_turn(row, cleared=header["status"] == "cleared")
        if header["status"] != "cleared" and input_hash(binding["workspace_id"], binding["actor_id"], thread_id, row["user_text"]) != row["input_hash"]:
            raise CommandRejected()
        row["action_receipt"] = self.chat_action_receipt(binding, row)
        return header, row

    def chat_send(self, binding, thread_id, request_id, text_value, now):
        identifiers(thread_id, request_id)
        message(text_value)
        digest = input_hash(binding["workspace_id"], binding["actor_id"], thread_id, text_value)
        exists = self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_thread
            WHERE workspace_id=:workspace_id AND thread_id=:thread)"""), {**binding, "thread": thread_id}).scalar_one()
        if not exists:
            title = next((line.strip()[:80] for line in text_value.splitlines() if line.strip()), "新对话")
            name(title)
            self._mutate(text("""INSERT INTO class_os.workspace_chat_thread
                (workspace_id,thread_id,owner_id,title,status,version,created_at,updated_at)
                VALUES(:workspace_id,:thread,:actor_id,:title,'active',1,:now,:now)"""),
                {**binding, "thread": thread_id, "title": title, "now": now})
        header = self.chat_header(binding, thread_id, active=True)
        existing = self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_turn
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND request_id=:request)"""),
            {**binding, "thread": thread_id, "request": request_id}).scalar_one()
        if existing:
            row = self._chat_turn(binding, thread_id, request_id)
            if row["input_hash"] != digest or row["user_text"] != text_value:
                raise CommandRejected()
            return row
        if self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_turn
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND state IN ('queued','running'))"""),
            {**binding, "thread": thread_id}).scalar_one():
            raise CommandRejected()
        ordinal = self._connection.execute(text("""SELECT coalesce(max(ordinal),0)+1 FROM class_os.workspace_chat_turn
            WHERE workspace_id=:workspace_id AND thread_id=:thread"""), {**binding, "thread": thread_id}).scalar_one()
        if ordinal > MAX_TURNS or now < header["updated_at"]:
            raise CommandRejected()
        self._mutate(text("""INSERT INTO class_os.workspace_chat_turn
            (workspace_id,thread_id,turn_id,request_id,ordinal,input_hash,user_text,state,version,created_at)
            VALUES(:workspace_id,:thread,:turn,:request,:ordinal,:hash,:body,'queued',1,:now)"""),
            {**binding, "thread": thread_id, "turn": uuid4(), "request": request_id, "ordinal": ordinal, "hash": digest, "body": text_value, "now": now})
        self._chat_touch(binding, thread_id, now)
        return self._chat_turn(binding, thread_id, request_id)

    def _chat_touch(self, binding, thread_id, now):
        self._mutate(text("""UPDATE class_os.workspace_chat_thread SET version=version+1,updated_at=:now
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread AND version<2147483647"""),
            {**binding, "thread": thread_id, "now": now})

    def chat_claim(self, binding, thread_id, request_id, now):
        self.chat_header(binding, thread_id, active=True)
        row = self._chat_turn(binding, thread_id, request_id)
        validate_turn(row)
        if input_hash(binding["workspace_id"], binding["actor_id"], thread_id, row["user_text"]) != row["input_hash"]:
            raise CommandRejected()
        if row["state"] != "queued":
            return None
        self._mutate(text("""UPDATE class_os.workspace_chat_turn SET state='running',version=version+1,
            generation=:generation,started_at=:now,lease_until=:lease
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND request_id=:request AND state='queued' AND version=:version"""),
            {**binding, "thread": thread_id, "request": request_id, "version": row["version"], "generation": uuid4(), "now": now, "lease": now + LEASE})
        return self._chat_turn(binding, thread_id, request_id)

    def chat_finish(self, binding, ticket, state, answer, proposed, now, duration_ms=None, input_tokens=None, output_tokens=None):
        if state not in TERMINAL:
            raise CommandRejected()
        row = self._chat_turn(binding, ticket["thread_id"], ticket["request_id"])
        self.chat_header(binding, row["thread_id"], active=True)
        if row["state"] != "running" or row["generation"] != ticket["generation"] or row["version"] != ticket["version"]:
            raise CommandRejected()
        if now >= row["lease_until"]:
            state, answer, proposed = "unknown", None, None
        if now < row["started_at"] or state != "completed" and (answer is not None or proposed is not None):
            raise CommandRejected()
        digest = None
        if state == "completed":
            message(answer, assistant=True)
            if proposed is not None:
                digest = candidate_hash(proposed)
        if any(value is not None and (type(value) is not int or not 0 <= value <= 2147483647) for value in (duration_ms, input_tokens, output_tokens)):
            raise CommandRejected()
        import json
        comparison = None
        if proposed is not None and self._store.database.profile == 'classroom-work-d4':
            from .change_preview import build_change_preview
            try:
                comparison = build_change_preview(self, binding, proposed, now)
            except CommandRejected:
                # The model may have read immediately before a concurrent
                # edit. Do not release a "ready" card without factual evidence.
                proposed, digest = None, None
                answer = '内容已变化，请重新生成这次操作。'
        self._mutate(text("""UPDATE class_os.workspace_chat_turn SET state=:state,version=version+1,assistant_text=:answer,
            candidate=CAST(:candidate AS jsonb),candidate_hash=:hash,ended_at=:now,duration_ms=:duration,input_tokens=:input_tokens,output_tokens=:output_tokens
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND request_id=:request AND version=:version AND generation=:generation"""),
            {**binding, "thread": row["thread_id"], "request": row["request_id"], "version": row["version"], "generation": row["generation"],
             "state": state, "answer": answer, "candidate": json.dumps(proposed, ensure_ascii=False) if proposed is not None else None,
             "hash": digest, "now": now, "duration": duration_ms, "input_tokens": input_tokens, "output_tokens": output_tokens})
        if comparison is not None:
            self._mutate(text('''UPDATE class_os.workspace_chat_turn SET change_preview=CAST(:comparison AS jsonb)
                WHERE workspace_id=:workspace_id AND thread_id=:thread AND request_id=:request AND candidate_hash=:hash'''),
                {**binding, 'thread': row['thread_id'], 'request': row['request_id'], 'hash': digest,
                 'comparison': json.dumps(comparison, ensure_ascii=False)})
        self._chat_touch(binding, row["thread_id"], now)
        return self._chat_turn(binding, row["thread_id"], row["request_id"])

    def chat_cancel(self, binding, thread_id, request_id, expected_version, now):
        self.chat_header(binding, thread_id, active=True)
        row = self._chat_turn(binding, thread_id, request_id)
        if row["state"] in TERMINAL:
            return row
        if row["version"] != expected_version or now < row["created_at"]:
            raise CommandRejected()
        self._mutate(text("""UPDATE class_os.workspace_chat_turn SET state='cancelled',version=version+1,ended_at=:now
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND request_id=:request AND version=:version"""),
            {**binding, "thread": thread_id, "request": request_id, "version": expected_version, "now": now})
        self._chat_touch(binding, thread_id, now)
        return self._chat_turn(binding, thread_id, request_id)

    def chat_control(self, binding, thread_id, expected_version, action, now):
        header = self.chat_header(binding, thread_id)
        if action not in ("archive", "clear") or header["version"] != expected_version or now < header["updated_at"]:
            raise CommandRejected()
        if header["status"] == "cleared" or action == "archive" and header["status"] != "active":
            raise CommandRejected()
        if self._connection.execute(text("""SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_turn
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND state IN ('queued','running'))"""), {**binding, "thread": thread_id}).scalar_one():
            raise CommandRejected()
        values = {**binding, "thread": thread_id, "now": now, "version": expected_version,
                  "state": "cleared" if action == "clear" else "archived", "cleared": now if action == "clear" else None}
        if action == "clear":
            if self._store.database.profile == 'classroom-work-d4':
                self._connection.execute(text('''UPDATE class_os.workspace_chat_turn SET change_preview=NULL
                    WHERE workspace_id=:workspace_id AND thread_id=:thread'''), values)
            self._connection.execute(text("""UPDATE class_os.workspace_chat_turn SET user_text=NULL,assistant_text=NULL,candidate=NULL,candidate_hash=NULL
                WHERE workspace_id=:workspace_id AND thread_id=:thread"""), values)
        self._mutate(text("""UPDATE class_os.workspace_chat_thread SET status=:state,version=version+1,updated_at=:now,cleared_at=:cleared
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread AND version=:version"""), values)
        return self.chat_header(binding, thread_id)


def validate_workspace_chat_integrity(connection):
    """Full fixed-table validation for trusted backup/restore and startup."""
    headers = {(row["workspace_id"], row["thread_id"]): dict(row) for row in connection.execute(text(
        "SELECT workspace_id,thread_id,owner_id,status FROM class_os.workspace_chat_thread")).mappings()}
    for row in connection.execute(text("SELECT * FROM class_os.workspace_chat_turn ORDER BY workspace_id,thread_id,ordinal")).mappings():
        header = headers.get((row["workspace_id"], row["thread_id"]))
        if header is None:
            raise ValueError("Orphan chat turn")
        validate_turn(row, cleared=header["status"] == "cleared")
        if header["status"] != "cleared" and input_hash(row["workspace_id"], header["owner_id"], row["thread_id"], row["user_text"]) != row["input_hash"]:
            raise ValueError("Persisted chat input mismatch")
