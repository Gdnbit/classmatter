"""Fixed source/initiative SQL under the existing QG/BCG serialized UoW."""
from datetime import timedelta
from uuid import uuid5

from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.personal_summary import (GOAL_RETRY_ACK, GOAL_TITLE, INITIATIVE_REQUEST, SUMMARY_TITLE, TITLE, SummaryDelegation,
    goal_material_reply, goal_recovery_basis, source_basis)
from .classroom_work import ClassroomTransaction


class PersonalSummaryTransaction(ClassroomTransaction):
    def _current_basis(self, binding, initiative, now):
        program = next((row for row in self.summary_programs(binding) if row['document_id'] == initiative['document_id']
                        and row['version'] == initiative['document_version']), None)
        if program is None:
            raise CommandRejected()
        if program.get('kind') == 'goal':
            _, program['goal_material'] = self._goal_material(binding, program)
            program['goal_retry'] = self._goal_retry(binding, program)
        try:
            basis, _ = source_basis(program, self.activity(binding['workspace_id'], program['class_id'], program['term_id'], now))
        except ValueError:
            raise CommandRejected() from None
        if basis != initiative['basis_hash'] and not (program.get('kind') == 'goal'
                and goal_recovery_basis(basis) == initiative['basis_hash']):
            raise CommandRejected()
        return program

    def _goal_material(self, binding, program, *, before=None):
        keys = {**binding, 'document': program['document_id'], 'version': program['version'],
                'thread': program['thread_id'], 'label': program['required_material'], 'before': before}
        ordinal = self._connection.execute(text('''SELECT max(q.ordinal) FROM class_os.personal_summary_attempt p
            JOIN class_os.workspace_chat_turn q ON q.workspace_id=p.workspace_id AND q.thread_id=p.thread_id
              AND q.request_id=p.waiting_request_id
            WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND p.document_id=:document
              AND p.document_version=:version AND p.thread_id=:thread AND p.answer_required AND q.state='completed'
              AND (CAST(:before AS integer) IS NULL OR q.ordinal<:before)'''), keys).scalar_one()
        if ordinal is None:
            return False, ''
        replies = self._connection.execute(text('''SELECT t.user_text FROM class_os.workspace_chat_turn t
            WHERE t.workspace_id=:workspace_id AND t.thread_id=:thread AND t.ordinal>:ordinal AND t.state='completed'
              AND left(t.user_text,char_length(:label))=:label
              AND (CAST(:before AS integer) IS NULL OR t.ordinal<:before)
            ORDER BY t.ordinal DESC LIMIT 20'''), {**keys, 'ordinal': ordinal}).scalars()
        return True, next((answer for reply in replies if (answer := goal_material_reply(reply, keys['label']))), '')

    def _goal_delivered(self, binding, program):
        latest = self._connection.execute(text('''SELECT t.candidate,t.candidate_hash FROM class_os.personal_summary_attempt p
            JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)
            WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND p.document_id=:document
              AND p.document_version=:version AND p.thread_id=:thread AND t.state='completed'
              AND t.candidate->>'command'='document.create' AND t.candidate->>'title'=:title
            ORDER BY t.ordinal DESC LIMIT 1'''), {**binding, 'document': program['document_id'], 'version': program['version'],
            'thread': program['thread_id'], 'title': program['deliverable']}).mappings().one_or_none()
        return latest is not None and self.chat_action_receipt(binding, latest) is not None

    def _goal_retry(self, binding, program):
        retry = self._connection.execute(text('''SELECT request_id FROM class_os.workspace_chat_turn
            WHERE workspace_id=:workspace_id AND thread_id=:thread AND ordinal>:ordinal AND state='completed'
              AND user_text='继续整理班级工作小结。' AND assistant_text=:ack
            ORDER BY ordinal DESC LIMIT 1'''), {**binding, 'thread': program['thread_id'],
            'ordinal': program['confirmed_ordinal'], 'ack': GOAL_RETRY_ACK}).scalar_one_or_none()
        return str(retry) if retry else ''

    def _document_title_exists(self, binding, class_id, term_id, title):
        return self._connection.execute(text('''SELECT EXISTS(
            SELECT 1 FROM class_os.working_document d JOIN class_os.working_document_revision r
            USING(workspace_id,document_id,version,status)
            WHERE d.workspace_id=:workspace_id AND d.class_id=:class AND d.term_id=:term AND r.title=:title)'''),
            {**binding, 'class': class_id, 'term': term_id, 'title': title}).scalar_one()

    def validate_document(self, binding, command, now):
        result = super().validate_document(binding, command, now)
        from class_os.domain.workspace_chat import candidate_hash
        payload = command.canonical()
        if payload.get('command') in ('document.create', 'document.revise'):
            digest = candidate_hash(payload)
            if payload['command'] == 'document.create' and payload['title'] == GOAL_TITLE and self._document_title_exists(
                    binding, command.class_id, command.term_id, GOAL_TITLE):
                raise CommandRejected()
            matches = self._connection.execute(text('''SELECT p.* FROM class_os.personal_summary_attempt p
                JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)
                WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND t.candidate_hash=:hash
                ORDER BY p.created_at DESC LIMIT 1'''),
                 {**binding, 'hash': digest}).mappings().one_or_none()
            if matches:
                program = self._current_basis(binding, matches, now)
                if program.get('kind') == 'goal' and (payload['command'] != 'document.create'
                        or payload['title'] != program['deliverable'] or not program['goal_material']
                        or self._goal_delivered(binding, program)
                        or self._document_title_exists(binding, program['class_id'], program['term_id'], program['deliverable'])):
                    raise CommandRejected()
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
        if result['data']:
            self._project_summary_attention(binding, result, self.summary_programs(binding))
        return result

    def _project_summary_attention(self, binding, result, programs):
        attention = set()
        for program in programs:
            if program.get('kind') == 'builtin':
                continue
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
            if latest['answer_required'] and latest['question_state'] == 'completed' and program.get('kind') == 'goal':
                pending = pending or not self._goal_material(binding, program)[1]
            elif latest['answer_required'] and latest['question_state'] == 'completed':
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

    def summary_programs(self, binding, *, include_paused=False):
        statement = text('''SELECT d.document_id,d.class_id,d.term_id,d.version,r.body,r.title
            FROM class_os.working_document d JOIN class_os.working_document_revision r
            USING(workspace_id,document_id,version,status)
            WHERE d.workspace_id=:workspace_id AND d.owner_id=:actor_id AND d.status='draft' AND r.title=:title
            ORDER BY d.document_id LIMIT 11''')
        rows = self._connection.execute(statement, {**binding, 'title': TITLE}).mappings().all()
        if len(rows) > 10:
            raise CommandRejected()
        rows += self._connection.execute(statement, {**binding, 'title': GOAL_TITLE}).mappings().all()[:10]
        result = []
        for value in rows:
            row = dict(value)
            try:
                parsed = SummaryDelegation.parse(row['body'])
            except ValueError:
                continue  # A similarly named ordinary document is not executable.
            goal = bool(parsed.deliverable)
            if goal != (row['title'] == GOAL_TITLE):
                continue
            context = self.class_context(binding['workspace_id'], row['class_id'], row['term_id'])
            if (parsed.state != 'enabled' and not include_paused) or not context or context['status'] != 'active' or context['term_status'] != 'active':
                continue
            import rfc8785
            from hashlib import sha256
            term = self.term_metadata(binding['workspace_id'], row['class_id'], row['term_id'])
            students = self.roster(binding['workspace_id'], row['class_id'], row['term_id'], self.authorized_at)
            row['context_basis'] = sha256(rfc8785.dumps({'class_version': context['version'], 'term_version': term.version,
                'students': [{'id': str(student.student_id), 'name': student.name, 'version': student.version, 'status': student.status}
                             for student in sorted(students, key=lambda student: str(student.student_id))]})).hexdigest()
            # The original human-confirmed candidate identifies the conversation.
            turns = self._connection.execute(text('''SELECT t.*,h.status AS chat_status FROM class_os.workspace_chat_turn t
                JOIN class_os.workspace_chat_thread h USING(workspace_id,thread_id)
                WHERE t.workspace_id=:workspace_id AND h.owner_id=:actor_id AND h.status IN ('active','archived')
                AND (:include_inactive OR h.status='active')
                AND t.state='completed' AND t.candidate->>'document_id'=:document
                AND t.candidate->>'command' IN ('document.create','document.revise')
                ORDER BY t.created_at DESC,t.ordinal DESC LIMIT 20'''),
                {**binding, 'document': str(row['document_id']), 'include_inactive': include_paused}).mappings().all()
            for turn in turns:
                receipt = self.chat_action_receipt(binding, turn)
                if receipt and receipt['resource_id'] == row['document_id'] and (not goal or receipt['version'] == row['version']):
                    row.update(thread_id=turn['thread_id'], chat_status=turn['chat_status'], style=parsed.style, state=parsed.state,
                               required_material=parsed.required_material)
                    if goal:
                        row.update(kind='goal', deliverable=parsed.deliverable, confirmed_ordinal=turn['ordinal'])
                    result.append(row)
                    break
        return result

    def summary_context(self, binding, thread_id, request_id):
        current = self._chat_turn(binding, thread_id, request_id)
        direct = self._initiative(binding, thread_id, request_id)
        retry = current['origin'] == 'user' and current['user_text'] == '继续整理班级工作小结。'
        if direct is None and retry:
            latest = self._connection.execute(text('''SELECT p.*,t.state FROM class_os.personal_summary_attempt p
                JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)
                WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND p.thread_id=:thread
                ORDER BY t.ordinal DESC LIMIT 1'''), {**binding, 'thread': thread_id}).mappings().one_or_none()
            if latest and latest['state'] in ('failed', 'unknown'):
                for program in self.summary_programs(binding):
                    if (program.get('kind') == 'goal' and program['document_id'] == latest['document_id']
                            and program['version'] == latest['document_version'] and not self._goal_delivered(binding, program)):
                        return {**program, 'goal_receiving': 'retry'}
        if direct is None:
            previous = self._connection.execute(text('''SELECT t.request_id FROM class_os.workspace_chat_turn t
                JOIN class_os.personal_summary_attempt p ON p.workspace_id=t.workspace_id
                  AND p.thread_id=t.thread_id AND p.waiting_request_id=t.request_id
                WHERE t.workspace_id=:workspace_id AND t.thread_id=:thread AND t.ordinal<:ordinal
                AND t.state='completed' AND p.owner_id=:actor_id AND p.answer_required
                AND (EXISTS(SELECT 1 FROM class_os.working_document_revision r WHERE r.workspace_id=p.workspace_id
                    AND r.document_id=p.document_id AND r.version=p.document_version AND r.title=:goal_title)
                  OR NOT EXISTS(SELECT 1 FROM class_os.workspace_chat_turn a WHERE a.workspace_id=t.workspace_id
                  AND a.thread_id=t.thread_id AND a.ordinal>t.ordinal AND a.ordinal<:ordinal AND a.state='completed'
                  AND a.candidate->>'title'=:summary_title AND a.candidate->>'command' IN ('document.create','document.revise')))
                ORDER BY t.ordinal DESC LIMIT 1'''),
                {**binding, 'thread': thread_id, 'ordinal': current['ordinal'], 'summary_title': SUMMARY_TITLE,
                 'goal_title': GOAL_TITLE}).scalar_one_or_none()
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
                if program.get('kind') == 'goal':
                    if current['origin'] == 'user':
                        reply = goal_material_reply(current['user_text'], program['required_material'])
                        if reply and not self._goal_delivered(binding, program) and self._goal_material(binding, program, before=current['ordinal'])[0]:
                            return {**program, 'goal_receiving': 'material'}
                        return None
                    _, program['goal_material'] = self._goal_material(binding, program)
                return {**program, 'basis_hash': direct['basis_hash'], 'initiative': current['origin'] == 'personal-agent'}
        if current['origin'] == 'user':
            return None  # An old paused question must not block ordinary chat.
        raise CommandRejected()  # A paused/replaced initiative cannot resume.

    def summary_claim(self, binding, document_id, now):
        program = next((row for row in self.summary_programs(binding) if row['document_id'] == document_id), None)
        if program is None:
            return None
        goal = program.get('kind') == 'goal'
        if goal:
            if self._goal_delivered(binding, program):
                return None
            waiting, program['goal_material'] = self._goal_material(binding, program)
            if waiting and not program['goal_material']:
                return None
            program['goal_retry'] = self._goal_retry(binding, program)
        projection = self.activity(binding['workspace_id'], program['class_id'], program['term_id'], now)
        basis, useful = source_basis(program, projection)
        recovery = goal_recovery_basis(basis) if goal else None
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
                if previous['basis_hash'] in (basis, recovery):
                    return self._chat_turn(binding, row['thread_id'], row['request_id'])
                self.chat_cancel(binding, row['thread_id'], row['request_id'], row['version'], now)
            elif now >= row['lease_until']:
                self.chat_finish(binding, row, 'unknown', None, None, now)
            else:
                return None
        if goal and self._connection.execute(text('''SELECT t.state FROM class_os.personal_summary_attempt p
                JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)
                WHERE p.workspace_id=:workspace_id AND p.document_id=:document AND p.basis_hash=:basis'''), values).scalar_one_or_none() == 'unknown':
            basis = values['basis'] = recovery  # At most one automatic recovery for identical persisted sources.
        if not useful or self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.personal_summary_attempt
            WHERE workspace_id=:workspace_id AND document_id=:document AND basis_hash=:basis)
            OR EXISTS(SELECT 1 FROM class_os.workspace_chat_turn WHERE workspace_id=:workspace_id
                AND thread_id=:thread AND state IN ('queued','running'))'''), values).scalar_one():
            return None
        recent = self._summary_recent(binding, now)
        if len(recent) >= 6 or recent and now - recent[0] < timedelta(minutes=1):
            return None
        request_id = uuid5(document_id, basis)
        turn = self.chat_send(binding, program['thread_id'], request_id, INITIATIVE_REQUEST, now)
        self._mutate(text('''INSERT INTO class_os.personal_summary_attempt
            (workspace_id,owner_id,document_id,document_version,thread_id,request_id,basis_hash,created_at)
            VALUES(:workspace_id,:actor_id,:document,:version,:thread,:request,:basis,:now)'''),
            {**values, 'version': program['version'], 'request': request_id})
        return self._chat_turn(binding, program['thread_id'], turn['request_id'])

    def _summary_recent(self, binding, now):
        return self._connection.execute(text('''SELECT created_at FROM class_os.personal_summary_attempt
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND created_at>:since
            ORDER BY created_at DESC LIMIT 7'''), {**binding, 'since': now - timedelta(days=1)}).scalars().all()

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
        delegation = SummaryDelegation.parse(row['body'])
        if row['title'] != (GOAL_TITLE if delegation.deliverable else TITLE) or delegation.state != 'enabled':
            raise ValueError('Initiative is not rooted in a standing instruction')
        if row['request_id'] != uuid5(row['document_id'], row['basis_hash']):
            raise ValueError('Initiative identity mismatch')
        if row['status'] != 'cleared' and row['user_text'] != INITIATIVE_REQUEST:
            raise ValueError('Initiative was mistaken for a human message')
        if row['answer_required'] and row['status'] != 'cleared' and (
                row['question_state'] != 'completed' or row['question_candidate'] is not None or not row['question_text']):
            raise ValueError('Invalid waiting question')
    if connection.execute(text('SELECT version_num FROM class_os.alembic_version')).scalar_one() in ('0033','0034'):
        from .builtin_summary_store import validate_builtin_summary_integrity
        validate_builtin_summary_integrity(connection)
