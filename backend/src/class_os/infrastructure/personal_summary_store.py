"""Fixed source/initiative SQL under the existing QG/BCG serialized UoW."""
from datetime import timedelta
from uuid import uuid5

from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.personal_summary import SummaryDelegation, TITLE, SUMMARY_TITLE, INITIATIVE_REQUEST, source_basis
from .classroom_work import ClassroomTransaction


class PersonalSummaryTransaction(ClassroomTransaction):
    def _current_basis(self, binding, initiative, now):
        program = next((row for row in self.summary_programs(binding) if row['document_id'] == initiative['document_id']
                        and row['version'] == initiative['document_version']), None)
        if program is None:
            raise CommandRejected()
        try:
            basis, _ = source_basis(program, self.activity(binding['workspace_id'], program['class_id'], program['term_id'], now))
        except ValueError:
            raise CommandRejected() from None
        if basis != initiative['basis_hash']:
            raise CommandRejected()

    def validate_document(self, binding, command, now):
        result = super().validate_document(binding, command, now)
        from class_os.domain.workspace_chat import candidate_hash
        if command.canonical().get('command') in ('document.create', 'document.revise'):
            matches = self._connection.execute(text('''SELECT p.* FROM class_os.personal_summary_attempt p
                JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)
                WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND t.candidate_hash=:hash
                ORDER BY p.created_at DESC LIMIT 1'''),
                {**binding, 'hash': candidate_hash(command.canonical())}).mappings().one_or_none()
            if matches:
                self._current_basis(binding, matches, now)
        return result

    def _initiative(self, binding, thread_id, request_id):
        row = self._connection.execute(text('''SELECT * FROM class_os.personal_summary_attempt
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread AND request_id=:request'''),
            {**binding, 'thread': thread_id, 'request': request_id}).mappings().one_or_none()
        return dict(row) if row else None

    def _chat_turn(self, binding, thread_id, request_id):
        row = super()._chat_turn(binding, thread_id, request_id)
        initiative = self._initiative(binding, thread_id, request_id)
        row['origin'] = 'personal-agent' if initiative else 'user'
        row['answer_required'] = bool(initiative and initiative['answer_required'])
        return row

    def chat_history(self, binding, thread_id, *, before=None):
        result = super().chat_history(binding, thread_id, before=before)
        for row in result['turns']:
            initiative = self._initiative(binding, thread_id, row['request_id'])
            row['origin'] = 'personal-agent' if initiative else 'user'
            row['answer_required'] = bool(initiative and initiative['answer_required'])
        return result

    def chat_list(self, binding, *, offset=0):
        result = super().chat_list(binding, offset=offset)
        attention = set()
        for program in self.summary_programs(binding):
            latest = self._connection.execute(text('''SELECT t.*,p.answer_required,q.ordinal AS question_ordinal,
                q.state AS question_state FROM class_os.personal_summary_attempt p
                JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)
                LEFT JOIN class_os.workspace_chat_turn q ON q.workspace_id=p.workspace_id
                  AND q.thread_id=p.thread_id AND q.request_id=p.waiting_request_id
                WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND p.document_id=:document
                ORDER BY p.created_at DESC,t.ordinal DESC LIMIT 1'''),
                {**binding, 'document': program['document_id']}).mappings().one_or_none()
            if not latest:
                continue
            pending = latest['state'] == 'completed' and latest['candidate'] is not None and self.chat_action_receipt(binding, latest) is None
            if latest['answer_required'] and latest['question_state'] == 'completed':
                answered = self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_turn t
                    WHERE t.workspace_id=:workspace_id AND t.thread_id=:thread AND t.ordinal>:ordinal AND t.state='completed'
                    AND t.candidate->>'title'=:summary_title AND t.candidate->>'command' IN ('document.create','document.revise')
                    AND NOT EXISTS(SELECT 1 FROM class_os.personal_summary_attempt p WHERE p.workspace_id=t.workspace_id
                      AND p.thread_id=t.thread_id AND p.request_id=t.request_id))'''),
                    {**binding, 'thread': latest['thread_id'], 'ordinal': latest['question_ordinal'], 'summary_title': SUMMARY_TITLE}).scalar_one()
                pending = pending or not answered
            if pending:
                attention.add(latest['thread_id'])
        for row in result['data']:
            row['summary_attention'] = row['thread_id'] in attention
        return result

    def summary_programs(self, binding):
        rows = self._connection.execute(text('''SELECT d.document_id,d.class_id,d.term_id,d.version,r.body
            FROM class_os.working_document d JOIN class_os.working_document_revision r
            USING(workspace_id,document_id,version,status)
            WHERE d.workspace_id=:workspace_id AND d.owner_id=:actor_id AND d.status='draft' AND r.title=:title
            ORDER BY d.document_id LIMIT 11'''), {**binding, 'title': TITLE}).mappings().all()
        if len(rows) > 10:
            raise CommandRejected()
        result = []
        for value in rows:
            row = dict(value)
            try:
                parsed = SummaryDelegation.parse(row['body'])
            except ValueError:
                continue  # A similarly named ordinary document is not executable.
            context = self.class_context(binding['workspace_id'], row['class_id'], row['term_id'])
            if parsed.state != 'enabled' or not context or context['status'] != 'active' or context['term_status'] != 'active':
                continue
            import rfc8785
            from hashlib import sha256
            term = self.term_metadata(binding['workspace_id'], row['class_id'], row['term_id'])
            students = self.roster(binding['workspace_id'], row['class_id'], row['term_id'], self.authorized_at)
            row['context_basis'] = sha256(rfc8785.dumps({'class_version': context['version'], 'term_version': term.version,
                'students': [{'id': str(student.student_id), 'name': student.name, 'version': student.version, 'status': student.status}
                             for student in sorted(students, key=lambda student: str(student.student_id))]})).hexdigest()
            # The original human-confirmed candidate identifies the conversation.
            turns = self._connection.execute(text('''SELECT t.* FROM class_os.workspace_chat_turn t
                JOIN class_os.workspace_chat_thread h USING(workspace_id,thread_id)
                WHERE t.workspace_id=:workspace_id AND h.owner_id=:actor_id AND h.status='active'
                AND t.state='completed' AND t.candidate->>'document_id'=:document
                AND t.candidate->>'command' IN ('document.create','document.revise')
                ORDER BY t.created_at DESC,t.ordinal DESC LIMIT 20'''),
                {**binding, 'document': str(row['document_id'])}).mappings().all()
            for turn in turns:
                receipt = self.chat_action_receipt(binding, turn)
                if receipt and receipt['resource_id'] == row['document_id']:
                    row.update(thread_id=turn['thread_id'], style=parsed.style,
                               required_material=parsed.required_material)
                    result.append(row)
                    break
        return result

    def summary_context(self, binding, thread_id, request_id):
        current = self._chat_turn(binding, thread_id, request_id)
        direct = self._initiative(binding, thread_id, request_id)
        if direct is None:
            previous = self._connection.execute(text('''SELECT t.request_id FROM class_os.workspace_chat_turn t
                JOIN class_os.personal_summary_attempt p ON p.workspace_id=t.workspace_id
                  AND p.thread_id=t.thread_id AND p.waiting_request_id=t.request_id
                WHERE t.workspace_id=:workspace_id AND t.thread_id=:thread AND t.ordinal<:ordinal
                AND t.state='completed' AND p.owner_id=:actor_id AND p.answer_required
                AND NOT EXISTS(SELECT 1 FROM class_os.workspace_chat_turn a WHERE a.workspace_id=t.workspace_id
                  AND a.thread_id=t.thread_id AND a.ordinal>t.ordinal AND a.ordinal<:ordinal AND a.state='completed'
                  AND a.candidate->>'title'=:summary_title AND a.candidate->>'command' IN ('document.create','document.revise'))
                ORDER BY t.ordinal DESC LIMIT 1'''),
                {**binding, 'thread': thread_id, 'ordinal': current['ordinal'], 'summary_title': SUMMARY_TITLE}).scalar_one_or_none()
            if previous:
                direct = self._connection.execute(text('''SELECT * FROM class_os.personal_summary_attempt
                    WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread
                    AND waiting_request_id=:request'''), {**binding, 'thread': thread_id, 'request': previous}).mappings().one()
        if direct is None and current['user_text'] == '继续整理班级工作小结。':
            # The original UI's explicit retry must retain its failed program
            # even when no question was emitted before the provider failed.
            direct = self._connection.execute(text('''SELECT p.* FROM class_os.personal_summary_attempt p
                JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)
                WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND p.thread_id=:thread
                AND t.state IN ('failed','unknown') ORDER BY t.ordinal DESC LIMIT 1'''),
                {**binding, 'thread': thread_id}).mappings().one_or_none()
        if direct is None:
            return None
        for program in self.summary_programs(binding):
            if program['document_id'] == direct['document_id'] and program['version'] == direct['document_version']:
                return {**program, 'basis_hash': direct['basis_hash'], 'initiative': current['origin'] == 'personal-agent'}
        if current['origin'] == 'user':
            return None  # An old paused question must not block ordinary chat.
        raise CommandRejected()  # A paused/replaced initiative cannot resume.

    def summary_claim(self, binding, document_id, now):
        program = next((row for row in self.summary_programs(binding) if row['document_id'] == document_id), None)
        if program is None:
            return None
        projection = self.activity(binding['workspace_id'], program['class_id'], program['term_id'], now)
        basis, useful = source_basis(program, projection)
        values = {**binding, 'document': document_id, 'basis': basis, 'thread': program['thread_id'], 'now': now}
        # A queued initiative has not entered the SDK and may safely resume.
        # A running/unknown attempt is never blindly dispatched after a crash.
        active = self._connection.execute(text('''SELECT t.* FROM class_os.workspace_chat_turn t
            JOIN class_os.personal_summary_attempt p USING(workspace_id,thread_id,request_id)
            WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND p.document_id=:document
            AND t.state IN ('queued','running')'''), values).mappings().all()
        for row in active:
            previous = self._initiative(binding, row['thread_id'], row['request_id'])
            if row['state'] == 'queued':
                if previous['basis_hash'] == basis:
                    return self._chat_turn(binding, row['thread_id'], row['request_id'])
                self.chat_cancel(binding, row['thread_id'], row['request_id'], row['version'], now)
            elif now >= row['lease_until']:
                self.chat_finish(binding, row, 'unknown', None, None, now)
            else:
                return None
        if not useful or self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.personal_summary_attempt
            WHERE workspace_id=:workspace_id AND document_id=:document AND basis_hash=:basis)
            OR EXISTS(SELECT 1 FROM class_os.workspace_chat_turn WHERE workspace_id=:workspace_id
                AND thread_id=:thread AND state IN ('queued','running'))'''), values).scalar_one():
            return None
        recent = self._connection.execute(text('''SELECT created_at FROM class_os.personal_summary_attempt
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND created_at>:since
            ORDER BY created_at DESC LIMIT 7'''), {**values, 'since': now - timedelta(days=1)}).scalars().all()
        if len(recent) >= 6 or recent and now - recent[0] < timedelta(minutes=1):
            return None
        request_id = uuid5(document_id, basis)
        turn = self.chat_send(binding, program['thread_id'], request_id, INITIATIVE_REQUEST, now)
        self._mutate(text('''INSERT INTO class_os.personal_summary_attempt
            (workspace_id,owner_id,document_id,document_version,thread_id,request_id,basis_hash,created_at)
            VALUES(:workspace_id,:actor_id,:document,:version,:thread,:request,:basis,:now)'''),
            {**values, 'version': program['version'], 'request': request_id})
        return self._chat_turn(binding, program['thread_id'], turn['request_id'])

    def chat_finish(self, binding, ticket, state, answer, proposed, now, duration_ms=None,
                    input_tokens=None, output_tokens=None, *, answer_required=False, summary_document_id=None):
        initiative = self._initiative(binding, ticket['thread_id'], ticket['request_id'])
        if initiative and state == 'completed':
            try:
                self._current_basis(binding, initiative, now)
            except CommandRejected:
                answer, proposed, answer_required = '材料或委托已更新，这份小结需要重新整理。', None, False
        row = super().chat_finish(binding, ticket, state, answer, proposed, now, duration_ms, input_tokens, output_tokens)
        if initiative is None and row['state'] == 'completed' and answer_required and summary_document_id:
            # A human-requested retry is still a human turn. Persist only the
            # link of its actual deferred question to the original initiative.
            program = next((p for p in self.summary_programs(binding) if p['document_id'] == summary_document_id
                and p['thread_id'] == ticket['thread_id']), None)
            if program:
                initiative = self._connection.execute(text('''SELECT * FROM class_os.personal_summary_attempt
                    WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND document_id=:document
                    AND document_version=:version AND thread_id=:thread ORDER BY created_at DESC LIMIT 1'''),
                    {**binding, 'document': summary_document_id, 'version': program['version'],
                     'thread': ticket['thread_id']}).mappings().one_or_none()
        if initiative:
            self._mutate(text('''UPDATE class_os.personal_summary_attempt SET answer_required=:required,
                waiting_request_id=:waiting
                WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread AND request_id=:request'''),
                {**binding, 'thread': ticket['thread_id'], 'request': initiative['request_id'],
                 'required': bool(row['state'] == 'completed' and answer_required),
                 'waiting': ticket['request_id'] if row['state'] == 'completed' and answer_required else None})
            row = self._chat_turn(binding, ticket['thread_id'], ticket['request_id'])
        return row


def validate_summary_integrity(connection):
    rows = connection.execute(text('''SELECT p.*,d.owner_id AS document_owner,h.owner_id AS chat_owner,t.state,
        t.candidate,t.assistant_text,t.user_text,h.status,r.title,r.body,
        q.state AS question_state,q.candidate AS question_candidate,q.assistant_text AS question_text
        FROM class_os.personal_summary_attempt p
        JOIN class_os.working_document d ON d.workspace_id=p.workspace_id AND d.document_id=p.document_id
        JOIN class_os.working_document_revision r ON r.workspace_id=p.workspace_id AND r.document_id=p.document_id AND r.version=p.document_version
        JOIN class_os.workspace_chat_thread h ON h.workspace_id=p.workspace_id AND h.thread_id=p.thread_id
        JOIN class_os.workspace_chat_turn t ON t.workspace_id=p.workspace_id AND t.thread_id=p.thread_id AND t.request_id=p.request_id
        LEFT JOIN class_os.workspace_chat_turn q ON q.workspace_id=p.workspace_id AND q.thread_id=p.thread_id AND q.request_id=p.waiting_request_id''')).mappings()
    for row in rows:
        if row['owner_id'] != row['document_owner'] or row['owner_id'] != row['chat_owner']:
            raise ValueError('Initiative owner mismatch')
        if row['title'] != TITLE or SummaryDelegation.parse(row['body']).state != 'enabled':
            raise ValueError('Initiative is not rooted in a standing instruction')
        if row['request_id'] != uuid5(row['document_id'], row['basis_hash']):
            raise ValueError('Initiative identity mismatch')
        if row['status'] != 'cleared' and row['user_text'] != INITIATIVE_REQUEST:
            raise ValueError('Initiative was mistaken for a human message')
        if row['answer_required'] and row['status'] != 'cleared' and (
                row['question_state'] != 'completed' or row['question_candidate'] is not None or not row['question_text']):
            raise ValueError('Invalid waiting question')
