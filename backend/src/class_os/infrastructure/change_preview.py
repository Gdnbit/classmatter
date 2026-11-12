"""Factual, fixed-query comparison builder inside the existing serialized BCG.

Frozen display values are evidence of a proposal, never current business facts.
The original command CAS and receipt remain the only authority for saving.
"""
from sqlalchemy import text
from class_os.domain.change_preview import ChangePreview
from class_os.application.roster import CommandRejected


def build_change_preview(tx, binding, payload, now):
    from class_os.domain.workspace_chat import candidate, candidate_hash
    from class_os.application.roster import BusinessGateway
    from class_os.domain.classroom_work import COMMANDS
    command = candidate(payload)
    if payload['command'] in COMMANDS:
        tx.validate_classroom(binding, command, now)
    elif payload['command'].startswith('document.'):
        tx.validate_document(binding, command, now)
    else:
        BusinessGateway._validate(tx, binding, command, now)
    values = {**binding, 'c': command.class_id, 't': command.term_id}
    kind, fields, before_seats, after_seats = 'edit', [], None, None

    def field(key, before, after):
        fields.append({'field': key, 'before': str(before) if before is not None else None,
                       'after': str(after) if after is not None else None})

    names = {}
    def student(student_id):
        if student_id is None:
            return None
        if student_id in names:
            return names[student_id]
        row = tx._connection.execute(text('''SELECT name FROM class_os.student
            WHERE workspace_id=:workspace_id AND student_id=:s'''), {**values, 's': student_id}).scalar_one()
        names[student_id] = row
        return row

    operation = payload['command']
    if operation in ('seat.layout.create', 'seat.assign', 'seat.swap'):
        kind = 'seating'
        previous = tx.read_seating(binding, command.class_id, command.term_id)
        def board(rows, columns, seats):
            return {'rows': rows, 'columns': columns, 'cells': [
                {'row': seat['row_index'], 'column': seat['column_index'], 'student': student(seat['student_id']),
                 'student_id': str(seat['student_id']) if seat['student_id'] else None} for seat in seats]}
        if previous:
            before_seats = board(previous['rows'], previous['columns'], previous['seats'])
            prepared = tx.validate_classroom(binding, command, now)
            after_seats = board(previous['rows'], previous['columns'], prepared)
        else:
            after_seats = board(command.rows, command.columns, [
                {'row_index': r, 'column_index': c, 'student_id': None}
                for r in range(1, command.rows + 1) for c in range(1, command.columns + 1)])
    elif operation == 'score.record':
        from decimal import Decimal
        exam = tx.read_exams(binding, command.class_id, command.term_id, command.exam_id)
        previous = next((row for row in exam['results'] if row['student_id'] == command.student_id), None)
        field('title', exam['title'], exam['title'])
        field('subject', exam['subject'], exam['subject'])
        field('student', student(command.student_id), student(command.student_id))
        field('score', previous['score'] if previous else None, format(Decimal(command.score), '.2f') if command.score is not None else None)
        field('status', previous['status'] if previous else 'not-recorded', command.status)
        field('reason', previous['reason'] if previous else None, command.reason)
    elif operation.startswith('document.'):
        previous = tx.read_documents(binding, command.class_id, command.term_id, command.document_id, False) if operation == 'document.revise' else None
        kind = 'edit' if previous else 'create'
        for key in ('title', 'body', 'format'):
            field(key, previous[key] if previous else None, payload[key])
    elif operation == 'record.create':
        kind = 'create'
        field('student', None, student(command.student_id))
        field('fact_text', None, command.fact_text)
        field('occurred_at', None, command.occurred_at.isoformat())
    elif operation.startswith('task.'):
        previous = tx.task(binding['workspace_id'], command.class_id, command.term_id, command.task_id) if operation != 'task.create' else None
        kind = 'edit' if previous else 'create'
        field('title', previous['title'] if previous else None, payload.get('title') or (previous['title'] if previous else None))
        field('status', previous['status'] if previous else None, payload.get('status', 'not-started'))
        due = payload.get('due_at') if not previous or payload.get('change_due_date') else previous['due_at']
        field('due_at', previous['due_at'] if previous else None, due)
        if not previous:
            field('student', None, student(command.student_id))
            if command.source_record_id:
                source = tx.latest_record(binding['workspace_id'], command.class_id, command.term_id, command.source_record_id)
                field('source', None, '\n'.join(value for value in (source['fact_text'], source['observation_text']) if value))
        else:
            field('evidence', previous['evidence'], payload['evidence'])
    elif operation == 'class.create':
        kind = 'create'
        for key in ('name', 'term_name', 'start_date', 'end_date'):
            field(key, None, payload[key])
    elif operation == 'class.update':
        previous = tx.current_context(binding['workspace_id'])
        field('name', previous.name, command.name)
    elif operation == 'term.update':
        previous = tx.term_metadata(binding['workspace_id'], command.class_id, command.term_id)
        for key in ('name', 'start_date', 'end_date'):
            field(key, getattr(previous, key), payload[key])
    elif operation.startswith('student.'):
        kind = 'create' if operation == 'student.create' else 'edit'
        field('name', None if kind == 'create' else student(command.student_id), command.name)
    elif operation == 'exam.create':
        kind = 'create'
        for key in ('title', 'subject', 'maximum_score'):
            field(key, None, payload[key])
    else:
        raise CommandRejected()
    return ChangePreview(candidate_hash=candidate_hash(payload), kind=kind, fields=fields,
                         before_seats=before_seats, after_seats=after_seats).model_dump()
