"""One system preparation task through existing QG/BCG and chat persistence."""
from datetime import timedelta
from hashlib import sha256
import re
from uuid import uuid5

import rfc8785
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.builtin_class_work import identifiers, REQUEST, INSTRUCTION, VERSION, TITLE
from class_os.domain.personal_summary import source_basis, SummaryDelegation, SUMMARY_TITLE, TITLE as PREFERENCE_TITLE
from .personal_summary_store import PersonalSummaryTransaction
from .workspace_chat import WorkspaceChatTransaction


class BuiltinSummaryTransaction(PersonalSummaryTransaction):
    def _builtin_program(self, binding):
        current = self.current_context(binding['workspace_id'])
        if current is None:
            return None
        term = self.term_metadata(binding['workspace_id'], current.class_id, current.term_id)
        students = self.roster(binding['workspace_id'], current.class_id, current.term_id, self.authorized_at)
        program_id, thread_id = identifiers(binding['workspace_id'], current.class_id, current.term_id)
        context = sha256(rfc8785.dumps({'class_version': current.version, 'term_version': term.version,
            'students': [{'id': str(s.student_id), 'name': s.name, 'version': s.version, 'status': s.status}
                         for s in sorted(students, key=lambda s: str(s.student_id))]})).hexdigest()
        return {'kind': 'builtin', 'program_id': program_id, 'document_id': None, 'version': VERSION,
                'class_id': current.class_id, 'term_id': current.term_id, 'thread_id': thread_id,
                'body': INSTRUCTION, 'style': 'standard', 'required_material': '', 'context_basis': context}

    def summary_programs(self, binding, *, include_paused=False):
        preferences = super().summary_programs(binding, include_paused=True)
        active = [row for row in preferences if row['state'] == 'enabled' and row['chat_status'] == 'active']
        builtin = self._builtin_program(binding)
        # A cleared instruction chat cannot supply execution authority, but its
        # remaining typed preference must not silently turn the default back on.
        has_preference = False
        if builtin:
            bodies = self._connection.execute(text('''SELECT r.body FROM class_os.working_document d
                JOIN class_os.working_document_revision r USING(workspace_id,document_id,version,status)
                WHERE d.workspace_id=:workspace_id AND d.owner_id=:actor_id AND d.class_id=:class
                  AND d.term_id=:term AND d.status='draft' AND r.title=:title'''),
                {**binding, 'class': builtin['class_id'], 'term': builtin['term_id'], 'title': PREFERENCE_TITLE}).scalars()
            for body in bodies:
                try:
                    has_preference = has_preference or not SummaryDelegation.parse(body).deliverable
                except ValueError:
                    pass
        if builtin and not has_preference:
            active.append(builtin)
        return preferences if include_paused else active

    def _initiative(self, binding, thread_id, request_id):
        explicit = super()._initiative(binding, thread_id, request_id)
        if explicit is not None:
            return explicit
        row = self._connection.execute(text('''SELECT * FROM class_os.builtin_summary_attempt
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread AND request_id=:request'''),
            {**binding, 'thread': thread_id, 'request': request_id}).mappings().one_or_none()
        return {**row, 'kind': 'builtin', 'answer_required': False, 'waiting_request_id': None} if row else None

    def _current_basis(self, binding, initiative, now):
        if initiative.get('kind') != 'builtin':
            return super()._current_basis(binding, initiative, now)
        program = next((row for row in self.summary_programs(binding) if row.get('program_id') == initiative['program_id']), None)
        if program is None or program['version'] != initiative['program_version']:
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
            attempt = self._connection.execute(text('''SELECT p.* FROM class_os.builtin_summary_attempt p
                JOIN class_os.workspace_chat_turn original USING(workspace_id,thread_id,request_id)
                JOIN class_os.workspace_chat_turn t ON t.workspace_id=p.workspace_id AND t.thread_id=p.thread_id
                WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND t.candidate_hash=:hash
                  AND (t.request_id=p.request_id OR t.ordinal>original.ordinal
                    AND original.state IN ('failed','unknown') AND t.user_text ~ '(重试|再试|继续.*小结)'
                    AND t.candidate->>'title'=:title)
                ORDER BY original.ordinal DESC LIMIT 1'''),
                {**binding, 'hash': candidate_hash(command.canonical()), 'title': SUMMARY_TITLE}).mappings().one_or_none()
            if attempt:
                self._current_basis(binding, {**attempt, 'kind': 'builtin'}, now)
        return result

    def summary_context(self, binding, thread_id, request_id):
        current = self._chat_turn(binding, thread_id, request_id)
        attempt = self._initiative(binding, thread_id, request_id)
        retry = False
        if attempt is None and current['origin'] == 'user' and re.search(r'重试|再试|继续.*小结', current['user_text'] or ''):
            attempt = self._connection.execute(text('''SELECT p.* FROM class_os.builtin_summary_attempt p
                JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)
                WHERE p.workspace_id=:workspace_id AND p.owner_id=:actor_id AND p.thread_id=:thread
                  AND t.state IN ('failed','unknown') ORDER BY t.ordinal DESC LIMIT 1'''),
                {**binding, 'thread': thread_id}).mappings().one_or_none()
            attempt = {**attempt, 'kind': 'builtin'} if attempt else None
            retry = attempt is not None
        if attempt is None or attempt.get('kind') != 'builtin':
            return super().summary_context(binding, thread_id, request_id)
        program = next((row for row in self.summary_programs(binding) if row.get('program_id') == attempt['program_id']), None)
        if program is None:
            if current['origin'] == 'user':
                return None
            raise CommandRejected()
        return {**program, 'basis_hash': attempt['basis_hash'], 'initiative': current['origin'] == 'personal-agent', 'resuming': retry}

    def summary_claim(self, binding, program_id, now):
        program = next((row for row in self.summary_programs(binding) if row.get('program_id') == program_id), None)
        if program is None:
            return super().summary_claim(binding, program_id, now)
        basis, useful = source_basis(program, self.activity(binding['workspace_id'], program['class_id'], program['term_id'], now))
        if not useful:
            return None
        values = {**binding, 'program': program_id, 'thread': program['thread_id'], 'basis': basis, 'now': now}
        header = self._connection.execute(text('''SELECT status FROM class_os.workspace_chat_thread
            WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread'''), values).scalar_one_or_none()
        if header is not None and (header != 'active' or not self._connection.execute(text('''SELECT EXISTS(
            SELECT 1 FROM class_os.builtin_summary_attempt WHERE workspace_id=:workspace_id
              AND owner_id=:actor_id AND program_id=:program AND thread_id=:thread)'''), values).scalar_one()):
            return None  # Never take over a human thread or resurrect a closed one.
        active = self._connection.execute(text('''SELECT t.* FROM class_os.workspace_chat_turn t
            WHERE t.workspace_id=:workspace_id AND t.thread_id=:thread AND t.state IN ('queued','running')'''), values).mappings().all()
        for row in active:
            previous = self._initiative(binding, row['thread_id'], row['request_id'])
            if not previous or previous.get('kind') != 'builtin':
                return None
            if row['state'] == 'queued':
                if previous['basis_hash'] == basis:
                    return self._chat_turn(binding, row['thread_id'], row['request_id'])
                self.chat_cancel(binding, row['thread_id'], row['request_id'], row['version'], now)
            elif now >= row['lease_until']:
                self.chat_finish(binding, row, 'unknown', None, None, now)
            else:
                return None
        if self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.builtin_summary_attempt
            WHERE workspace_id=:workspace_id AND program_id=:program AND basis_hash=:basis)'''), values).scalar_one():
            return None
        recent = self._summary_recent(binding, now)
        if len(recent) >= 6 or recent and now - recent[0] < timedelta(minutes=1):
            return None
        request_id = uuid5(program_id, basis)
        turn = self.chat_send(binding, program['thread_id'], request_id, REQUEST, now)
        if header is None:
            self._mutate(text('''UPDATE class_os.workspace_chat_thread SET title=:title
                WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND thread_id=:thread'''), {**values, 'title': TITLE})
        self._mutate(text('''INSERT INTO class_os.builtin_summary_attempt
            (workspace_id,owner_id,class_id,term_id,program_id,program_version,thread_id,request_id,basis_hash,created_at)
            VALUES(:workspace_id,:actor_id,:class,:term,:program,:version,:thread,:request,:basis,:now)'''),
            {**values, 'class': program['class_id'], 'term': program['term_id'], 'version': VERSION, 'request': request_id})
        return self._chat_turn(binding, program['thread_id'], turn['request_id'])

    def _summary_recent(self, binding, now):
        return self._connection.execute(text('''SELECT created_at FROM (
            SELECT created_at FROM class_os.personal_summary_attempt WHERE workspace_id=:workspace_id AND owner_id=:actor_id
            UNION ALL SELECT created_at FROM class_os.builtin_summary_attempt WHERE workspace_id=:workspace_id AND owner_id=:actor_id
            ) a WHERE created_at>:since ORDER BY created_at DESC LIMIT 7'''),
            {**binding, 'since': now - timedelta(days=1)}).scalars().all()

    def chat_finish(self, binding, ticket, state, answer, proposed, now, duration_ms=None,
                    input_tokens=None, output_tokens=None, *, answer_required=False, summary_document_id=None):
        initiative = self._initiative(binding, ticket['thread_id'], ticket['request_id'])
        if not initiative or initiative.get('kind') != 'builtin':
            return super().chat_finish(binding, ticket, state, answer, proposed, now, duration_ms,
                input_tokens, output_tokens, answer_required=answer_required, summary_document_id=summary_document_id)
        if answer_required:
            raise CommandRejected()  # No invented required topic or untracked question.
        if state == 'completed':
            try:
                self._current_basis(binding, initiative, now)
            except CommandRejected:
                answer, proposed = '记录有更新，重新整理后再核对。', None
        return WorkspaceChatTransaction.chat_finish(self, binding, ticket, state, answer, proposed, now,
                                                    duration_ms, input_tokens, output_tokens)

    def _project_summary_attention(self, binding, result, programs):
        super()._project_summary_attention(binding, result, programs)
        page_threads = {row['thread_id'] for row in result['data']}
        for program in programs:
            if program.get('kind') != 'builtin' or program['thread_id'] not in page_threads:
                continue
            latest = self._connection.execute(text('''SELECT t.* FROM class_os.workspace_chat_turn t
                WHERE t.workspace_id=:workspace_id AND t.thread_id=:thread AND
                  (EXISTS(SELECT 1 FROM class_os.builtin_summary_attempt p WHERE p.workspace_id=t.workspace_id
                    AND p.thread_id=t.thread_id AND p.request_id=t.request_id AND p.owner_id=:actor_id AND p.program_id=:program)
                   OR t.user_text ~ '(重试|再试|继续.*小结)' AND t.candidate->>'title'=:title)
                ORDER BY t.ordinal DESC LIMIT 1'''), {**binding, 'program': program['program_id'],
                    'thread': program['thread_id'], 'title': SUMMARY_TITLE}).mappings().one_or_none()
            pending = latest and latest['state'] == 'completed' and latest['candidate'] is not None and self.chat_action_receipt(binding, latest) is None
            if latest and latest['state'] == 'completed' and latest['candidate'] is None:
                visible = self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.workspace_chat_turn t
                    WHERE t.workspace_id=:workspace_id AND t.thread_id=:thread AND
                      (t.candidate IS NOT NULL OR t.state IN ('failed','unknown','cancelled') OR NOT EXISTS(
                        SELECT 1 FROM class_os.builtin_summary_attempt p WHERE p.workspace_id=t.workspace_id
                          AND p.thread_id=t.thread_id AND p.request_id=t.request_id)))'''),
                    {**binding, 'thread': program['thread_id']}).scalar_one()
                if not visible:
                    result['data'] = [row for row in result['data'] if row['thread_id'] != program['thread_id']]
            for row in result['data']:
                if row['thread_id'] == program['thread_id']:
                    row['summary_attention'] = row['summary_attention'] or bool(pending)


def validate_builtin_summary_integrity(connection):
    rows = connection.execute(text('''SELECT p.*,h.owner_id AS chat_owner,h.status,t.user_text
        FROM class_os.builtin_summary_attempt p
        JOIN class_os.workspace_chat_thread h USING(workspace_id,thread_id)
        JOIN class_os.workspace_chat_turn t USING(workspace_id,thread_id,request_id)''')).mappings()
    for row in rows:
        program, thread = identifiers(row['workspace_id'], row['class_id'], row['term_id'])
        if (row['program_version'] != VERSION or row['program_id'] != program or row['thread_id'] != thread
                or row['request_id'] != uuid5(program, row['basis_hash']) or row['owner_id'] != row['chat_owner']
                or row['status'] != 'cleared' and row['user_text'] != REQUEST):
            raise ValueError('Invalid built-in summary execution evidence')
