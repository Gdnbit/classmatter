"""D4 fixed ordinary-fact and follow-up tools. No write/approval/store handles."""
from datetime import datetime
from typing import Literal
from uuid import uuid4
from pydantic_ai import ModelRetry

from class_os.domain.activity import CreateRecord, CreateTask, ChangeTask, instant


def tools(capture, query, credentials, context, execute, missing_class):
    def latest_request():
        return next((message for message in reversed(capture.user_messages)
                     if message != '继续完成上面的任务，只处理尚未完成的步骤。'), '')

    def person(current, name):
        rows = query.roster(*credentials, current.class_id, current.term_id)
        matches = [row for row in rows if row.name == name and row.status == 'active']
        if not matches and name:
            # Recover a model-shortened label only when the teacher explicitly
            # supplied one unique current canonical name. No fuzzy matching or
            # permanent alias inference, including from earlier conversations.
            matches = [row for row in rows if row.status == 'active' and row.name in latest_request() and name in row.name]
        return matches[0] if len(matches) == 1 else None

    def records(current, student_id=None):
        rows = query.projection(*credentials, current.class_id, current.term_id, student_id=student_id)['records']
        latest = {}
        for row in rows:
            if row['record_id'] not in latest or row['version'] > latest[row['record_id']]['version']:
                latest[row['record_id']] = row
        return [row for row in latest.values() if row['kind'] == 'ordinary_fact' and row['revision_kind'] != 'supersede']

    async def read_class_records(student_name: str = '', search: str = '') -> dict:
        """Read confirmed ordinary student facts and source IDs/versions. This is not a complete school search; no health, disciplinary or inferred profiles. Never treats chat as a fact."""
        def read():
            current = context()
            if current is None:
                return missing_class
            student = person(current, student_name) if student_name else None
            if student_name and student is None:
                return {'status': 'needs-disambiguation', 'question': '没有找到唯一的学生，请确认姓名。'}
            names = {row.student_id: row.name for row in query.roster(*credentials, current.class_id, current.term_id)}
            rows = [row for row in records(current, student.student_id if student else None) if not search or search in row['fact_text']]
            return {'class_name': current.name, 'items': [
                {'record_id': str(row['record_id']), 'version': row['version'], 'student': names.get(row['student_id'], '历史学生'),
                 'fact_text': row['fact_text'], 'occurred_at': row['occurred_at'].isoformat()} for row in rows[:30]],
                'truncated': len(rows) > 30, 'scope': 'ordinary-facts-only',
                'instruction': 'Cite the returned student, fact and date in readable language. Retain source IDs/versions for verification; do not display internal IDs. Report scope and missing data honestly.'}
        return await execute('read_class_records', read)

    async def prepare_record(student_name: str, fact_text: str, occurred_at: str = '', occurred_now: bool = False) -> dict:
        """Prepare one already-occurred ordinary student fact. Copy fact_text as an EXACT contiguous quote from the latest meaningful user request, with no paraphrase or added punctuation; keep unrelated plans/personal notes out. Copy the full student name. For explicit 现在/刚刚 set occurred_now=true and leave occurred_at empty; otherwise use an ISO timestamp explicitly quoted by the user. Never infer time, diagnoses, responsibility or permanent memory; never saves."""
        def prepare():
            current = context()
            if current is None:
                return missing_class
            if not capture.mentioned(student_name):
                return {'status': 'needs-information', 'question': '要记录哪位学生的哪件事？'}
            if not fact_text.strip() or fact_text not in latest_request():
                # Invalid model arguments are not proof the teacher omitted
                # information. Let the existing bounded SDK correct its quote.
                raise ModelRetry('fact_text is not an exact quote. Copy a contiguous original quote without paraphrase or added punctuation, and use the full student name from this current user request: '
                    + latest_request() + '\nDo not ask the user to repeat information already provided. If no factual account was given, ask what happened; never invent one.')
            student = person(current, student_name)
            if student is None:
                return {'status': 'needs-disambiguation', 'question': '没有找到唯一的学生，请确认姓名。'}
            if capture.user_messages[-1:] == ('继续完成上面的任务，只处理尚未完成的步骤。',) and not occurred_at:
                existing = [row for row in records(current, student.student_id) if row['fact_text'] == fact_text
                            and str(row['record_id']) in capture.committed_record_ids]
                if len(existing) == 1:
                    row = existing[0]
                    return {'status': 'existing-record', 'record_id': str(row['record_id']), 'version': row['version'],
                        'student': student.name, 'fact_text': row['fact_text'], 'occurred_at': row['occurred_at'].isoformat(),
                        'instruction': 'This exact ordinary fact is already saved. Reuse its verified source for the next unfinished requested step. No new record was prepared; do not ask for its time again.'}
            when = None
            if occurred_now and not occurred_at and any(marker in capture.user_messages[-1] for marker in ('现在', '刚刚')):
                when = query.clock()
            elif not occurred_now and occurred_at and capture.mentioned(occurred_at):
                try:
                    when = instant(datetime.fromisoformat(occurred_at))
                except ValueError:
                    pass
            if when is None:
                return {'status': 'needs-information', 'question': '这件事是什么时候发生的？'}
            if any(row['fact_text'] == fact_text and row['occurred_at'] == when for row in records(current, student.student_id)):
                return {'status': 'existing-record', 'instruction': 'This exact fact and time are already recorded. Reuse the record.'}
            return capture.propose(CreateRecord('record.create', uuid4(), current.class_id, current.term_id,
                student.student_id, 'ordinary_fact', when, fact_text, ''))
        return await execute('prepare_record', prepare)

    async def prepare_task(action: Literal['create', 'edit', 'complete', 'cancel'], title: str, new_title: str = '',
                           status: Literal['not-started', 'in-progress', 'waiting'] | None = None, evidence: str = '',
                           student_name: str = '', source_fact: str = '', due_at: str = '', change_due_date: bool = False) -> dict:
        """Prepare one manual task, never save/send/delegate. Complete/cancel requires the user's quoted result/reason. For linked creation FIRST read_class_records and copy one confirmed ordinary fact's full student name and exact fact_text into source_fact. Never paraphrase the source. Deadline must be an explicit ISO timestamp, never invented. Only edits may change an existing deadline; change_due_date with empty due_at explicitly removes it."""
        def prepare():
            current = context()
            if current is None:
                return missing_class
            if not capture.mentioned(title) or new_title and not capture.mentioned(new_title):
                return {'status': 'needs-information', 'question': '任务的新标题是什么？' if capture.mentioned(title) else '要处理哪项任务？'}
            if (evidence and not capture.mentioned(evidence)
                    or action in ('complete', 'cancel') and (not evidence.strip() or evidence not in latest_request())):
                return {'status': 'needs-information', 'question': '请补充实际完成结果。' if action == 'complete' else '请补充跟进情况或取消原因。'}
            deadline = None
            if due_at:
                try:
                    if not capture.mentioned(due_at):
                        raise ValueError()
                    deadline = instant(datetime.fromisoformat(due_at))
                except ValueError:
                    return {'status': 'needs-information', 'question': '请确认截止日期和时间。'}
            if action in ('complete', 'cancel') and (new_title or status is not None or due_at or change_due_date or source_fact or student_name):
                return {'status': 'needs-information', 'question': '先核对结束结果，其他修改请单独处理。'}
            rows = query.projection(*credentials, current.class_id, current.term_id)['tasks']
            if action == 'create':
                if new_title or status is not None or evidence or change_due_date:
                    return {'status': 'needs-information', 'question': '先建立待办，再记录跟进情况。'}
                if any(row['title'] == title for row in rows):
                    return {'status': 'existing-task', 'instruction': 'This task title already exists. Read and reuse it; do not repeat creation.'}
                if (not source_fact and capture.committed_record_ids
                        and capture.user_messages[-1:] == ('继续完成上面的任务，只处理尚未完成的步骤。',)):
                    return {'status': 'read-source-first',
                        'instruction': 'This continuation has verified saved ordinary records. Before preparing a follow-up, call read_class_records and copy the intended source fact_text and full student name into source_fact/student_name. Do not silently drop the requested source. If the next task is independent, ask the user to confirm that in a new message; do not attach an unrelated record just to pass.'}
                student, source = None, None
                if source_fact and not student_name:
                    return {'status': 'needs-information', 'question': '这条记录属于哪位学生？'}
                if student_name:
                    student = person(current, student_name)
                    if student is None or not capture.mentioned(student_name):
                        return {'status': 'needs-disambiguation', 'question': '没有找到唯一的学生，请确认姓名。'}
                if source_fact:
                    matches = [row for row in records(current, student.student_id) if row['fact_text'] == source_fact]
                    if len(matches) != 1:
                        return {'status': 'needs-disambiguation', 'question': '没有找到唯一的已保存记录，请核对内容。'}
                    source = matches[0]['record_id']
                return capture.propose(CreateTask('task.create', uuid4(), current.class_id, current.term_id, title,
                    deadline, student.student_id if student else None, source))
            if student_name or source_fact:
                return {'status': 'needs-information', 'question': '已有任务的关联记录保持不变，请核对要修改的内容。'}
            matches = [row for row in rows if row['title'] == title and row['status'] not in ('done', 'cancelled')]
            if len(matches) != 1:
                return {'status': 'needs-disambiguation', 'question': '没有找到唯一的未完成任务，请确认标题。'}
            row = matches[0]
            if action in ('complete', 'cancel'):
                return capture.propose(ChangeTask('task.' + action, row['task_id'], current.class_id, current.term_id,
                    row['version'], 'done' if action == 'complete' else 'cancelled', evidence))
            if due_at and not change_due_date:
                return {'status': 'needs-information', 'question': '要同时修改截止时间吗？'}
            return capture.propose(ChangeTask('task.update', row['task_id'], current.class_id, current.term_id,
                row['version'], status or row['status'], evidence=evidence or row['evidence'], title=new_title or row['title'],
                due_at=deadline, change_due_date=change_due_date))
        return await execute('prepare_task', prepare)

    return read_class_records, prepare_record, prepare_task
