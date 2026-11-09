"""Fixed exam/seat SQL in the existing serialized business transaction."""
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import text

from class_os.application.roster import CommandRejected
from class_os.domain.roster import Receipt
from class_os.domain.classroom_work import CreateExam, RecordScore, CreateSeatLayout, AssignSeat, SwapSeats, score_value
from .workspace_chat import WorkspaceChatTransaction


class ClassroomTransaction(WorkspaceChatTransaction):
    def _classroom_context(self, binding, class_id, term_id, *, write=False):
        context = self.class_context(binding['workspace_id'], class_id, term_id)
        if not context or write and (context['status'] != 'active' or context['term_status'] != 'active'):
            raise CommandRejected()

    def _exam(self, binding, class_id, term_id, exam_id):
        row = self._connection.execute(text('''SELECT * FROM class_os.class_exam WHERE workspace_id=:workspace_id
            AND owner_id=:actor_id AND class_id=:c AND term_id=:t AND exam_id=:e'''),
            {**binding, 'c': class_id, 't': term_id, 'e': exam_id}).mappings().one_or_none()
        if row is None:
            raise CommandRejected()
        return dict(row)

    def _enrollment(self, binding, class_id, term_id, student_id):
        value = self._connection.execute(text('''SELECT e.enrollment_id FROM class_os.enrollment e
            JOIN class_os.student s USING(workspace_id,student_id)
            WHERE e.workspace_id=:workspace_id AND e.class_id=:c AND e.term_id=:t AND e.student_id=:s
            AND e.status='active' AND e.valid_to IS NULL AND s.status='active' '''),
            {**binding, 'c': class_id, 't': term_id, 's': student_id}).scalar_one_or_none()
        if value is None:
            raise CommandRejected()
        return value

    def _layout(self, binding, class_id, term_id, layout_id=None):
        row = self._connection.execute(text('''SELECT * FROM class_os.class_seating WHERE workspace_id=:workspace_id
            AND owner_id=:actor_id AND class_id=:c AND term_id=:t
            AND (CAST(:l AS uuid) IS NULL OR layout_id=:l)'''),
            {**binding, 'c': class_id, 't': term_id, 'l': layout_id}).mappings().one_or_none()
        return dict(row) if row else None

    def _seats(self, binding, layout):
        return [dict(row) for row in self._connection.execute(text('''SELECT row_index,column_index,student_id,enrollment_id
            FROM class_os.seat_revision WHERE workspace_id=:workspace_id AND layout_id=:l AND version=:v
            ORDER BY row_index,column_index'''), {**binding, 'l': layout['layout_id'], 'v': layout['version']}).mappings()]

    def validate_classroom(self, binding, command, now):
        self._classroom_context(binding, command.class_id, command.term_id, write=True)
        values = {**binding, 'c': command.class_id, 't': command.term_id}
        if type(command) is CreateExam:
            if self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.class_exam
                WHERE workspace_id=:workspace_id AND (exam_id=:e OR (class_id=:c AND term_id=:t AND title=:title AND subject=:subject)))'''),
                {**values, 'e': command.exam_id, 'title': command.title, 'subject': command.subject}).scalar_one():
                raise CommandRejected()
            return None
        if type(command) is RecordScore:
            exam = self._exam(binding, command.class_id, command.term_id, command.exam_id)
            enrollment = self._enrollment(binding, command.class_id, command.term_id, command.student_id)
            previous = self._connection.execute(text('''SELECT version,created_at FROM class_os.exam_result_revision
                WHERE workspace_id=:workspace_id AND exam_id=:e AND student_id=:s ORDER BY version DESC LIMIT 1'''),
                {**binding, 'e': command.exam_id, 's': command.student_id}).mappings().one_or_none()
            if (command.expected_version != (previous['version'] if previous else 0) or now < exam['updated_at']
                    or previous and now < previous['created_at']
                    or command.score is not None and score_value(command.score) > exam['maximum_score']):
                raise CommandRejected()
            return enrollment
        current = self._layout(binding, command.class_id, command.term_id)
        if type(command) is CreateSeatLayout:
            if current or self._connection.execute(text('''SELECT EXISTS(SELECT 1 FROM class_os.class_seating
                WHERE workspace_id=:workspace_id AND layout_id=:l)'''), {**binding, 'l': command.layout_id}).scalar_one():
                raise CommandRejected()
            return None
        if not current or current['layout_id'] != command.layout_id or current['version'] != command.expected_version or now < current['updated_at']:
            raise CommandRejected()
        seats = self._seats(binding, current)
        if len(seats) != current['rows'] * current['columns']:
            raise CommandRejected()
        by_position = {(row['row_index'], row['column_index']): row for row in seats}
        if type(command) is AssignSeat:
            target = by_position.get((command.row, command.column))
            if target is None or target['student_id'] is not None:
                raise CommandRejected()
            enrollment = self._enrollment(binding, command.class_id, command.term_id, command.student_id)
            for row in seats:
                if row['student_id'] == command.student_id:
                    row['student_id'] = row['enrollment_id'] = None
            target['student_id'], target['enrollment_id'] = command.student_id, enrollment
        elif type(command) is SwapSeats:
            left = by_position.get((command.first_row, command.first_column))
            right = by_position.get((command.second_row, command.second_column))
            if left is None or right is None or left['student_id'] is right['student_id'] is None:
                raise CommandRejected()
            for row in (left, right):
                if row['student_id']:
                    self._enrollment(binding, command.class_id, command.term_id, row['student_id'])
            left['student_id'], right['student_id'] = right['student_id'], left['student_id']
            left['enrollment_id'], right['enrollment_id'] = right['enrollment_id'], left['enrollment_id']
        else:
            raise CommandRejected()
        return seats

    def apply(self, binding, command, now):
        if type(command) not in (CreateExam, RecordScore, CreateSeatLayout, AssignSeat, SwapSeats):
            return super().apply(binding, command, now)
        prepared = self.validate_classroom(binding, command, now)
        values = {**binding, 'c': command.class_id, 't': command.term_id, 'now': now}
        if type(command) is CreateExam:
            self._mutate(text('''INSERT INTO class_os.class_exam
                (workspace_id,exam_id,owner_id,class_id,term_id,title,subject,maximum_score,version,created_at,updated_at)
                VALUES(:workspace_id,:e,:actor_id,:c,:t,:title,:subject,:maximum,1,:now,:now)'''),
                {**values, 'e': command.exam_id, 'title': command.title, 'subject': command.subject, 'maximum': score_value(command.maximum_score)})
            return Receipt(uuid4(), command.exam_id, 1)
        if type(command) is RecordScore:
            version = command.expected_version + 1
            self._mutate(text('''INSERT INTO class_os.exam_result_revision
                (workspace_id,exam_id,class_id,term_id,student_id,enrollment_id,version,status,score,reason,created_by,created_at)
                VALUES(:workspace_id,:e,:c,:t,:s,:enrollment,:v,:status,:score,:reason,:actor_id,:now)'''),
                {**values, 'e': command.exam_id, 's': command.student_id, 'enrollment': prepared, 'v': version,
                 'status': command.status, 'score': score_value(command.score) if command.score is not None else None, 'reason': command.reason})
            self._mutate(text('''UPDATE class_os.class_exam SET version=version+1,updated_at=:now
                WHERE workspace_id=:workspace_id AND exam_id=:e'''), {**values, 'e': command.exam_id})
            return Receipt(uuid4(), command.student_id, version)
        if type(command) is CreateSeatLayout:
            version = 1
            self._mutate(text('''INSERT INTO class_os.class_seating
                (workspace_id,layout_id,owner_id,class_id,term_id,rows,columns,version,created_at,updated_at)
                VALUES(:workspace_id,:l,:actor_id,:c,:t,:rows,:columns,1,:now,:now)'''),
                {**values, 'l': command.layout_id, 'rows': command.rows, 'columns': command.columns})
            prepared = [{'row_index': r, 'column_index': c, 'student_id': None, 'enrollment_id': None}
                        for r in range(1, command.rows + 1) for c in range(1, command.columns + 1)]
        else:
            version = command.expected_version + 1
            self._mutate(text('''UPDATE class_os.class_seating SET version=:v,updated_at=:now
                WHERE workspace_id=:workspace_id AND layout_id=:l AND version=:old'''),
                {**values, 'l': command.layout_id, 'v': version, 'old': command.expected_version})
        statement = text('''INSERT INTO class_os.seat_revision
            (workspace_id,layout_id,class_id,term_id,version,row_index,column_index,student_id,enrollment_id,created_by,created_at)
            VALUES(:workspace_id,:l,:c,:t,:v,:row_index,:column_index,:student_id,:enrollment_id,:actor_id,:now)''')
        for row in prepared:
            self._mutate(statement, {**values, 'l': command.layout_id, 'v': version, **row})
        return Receipt(uuid4(), command.layout_id, version)

    def read_exams(self, binding, class_id, term_id, exam_id=None):
        self._classroom_context(binding, class_id, term_id)
        if exam_id is None:
            rows = [dict(row) for row in self._connection.execute(text('''SELECT exam_id,title,subject,maximum_score,version
                FROM class_os.class_exam WHERE workspace_id=:workspace_id AND owner_id=:actor_id AND class_id=:c AND term_id=:t
                ORDER BY created_at DESC,exam_id LIMIT 51'''), {**binding, 'c': class_id, 't': term_id}).mappings()]
            return {'exams': [{**row, 'maximum_score': str(row['maximum_score'])} for row in rows[:50]], 'truncated': len(rows) > 50}
        exam = self._exam(binding, class_id, term_id, exam_id)
        rows = [dict(row) for row in self._connection.execute(text('''SELECT DISTINCT ON(student_id)
            student_id,version,status,score,reason,created_at FROM class_os.exam_result_revision
            WHERE workspace_id=:workspace_id AND exam_id=:e ORDER BY student_id,version DESC'''),
            {**binding, 'e': exam_id}).mappings()]
        scored = [row['score'] for row in rows if row['status'] == 'scored']
        return {'exam_id': exam_id, 'title': exam['title'], 'subject': exam['subject'], 'maximum_score': str(exam['maximum_score']),
            'version': exam['version'], 'results': [{**row, 'score': str(row['score']) if row['score'] is not None else None} for row in rows],
            'scored_count': len(scored), 'average': str((sum(scored, Decimal(0)) / len(scored)).quantize(Decimal('.01'))) if scored else None}

    def read_seating(self, binding, class_id, term_id):
        self._classroom_context(binding, class_id, term_id)
        current = self._layout(binding, class_id, term_id)
        if current is None:
            return None
        return {key: current[key] for key in ('layout_id', 'rows', 'columns', 'version')} | {'seats': self._seats(binding, current)}


def validate_classroom_integrity(connection):
    """Complete fixed-table validation for startup/checkpoint, never a repair."""
    exams = {(row['workspace_id'], row['exam_id']): dict(row) for row in connection.execute(text('SELECT * FROM class_os.class_exam')).mappings()}
    counts, previous = {}, {}
    for row in connection.execute(text('SELECT * FROM class_os.exam_result_revision ORDER BY workspace_id,exam_id,student_id,version')).mappings():
        key = (row['workspace_id'], row['exam_id'])
        exam = exams[key]
        student_key = (*key, row['student_id'])
        prior = previous.get(student_key)
        if (row['version'] != (prior['version'] + 1 if prior else 1)
                or row['score'] is not None and row['score'] > exam['maximum_score']
                or row['created_at'] < (prior['created_at'] if prior else exam['created_at'])
                or row['created_at'] > exam['updated_at']):
            raise ValueError('Invalid result history')
        RecordScore(row['exam_id'], row['class_id'], row['term_id'], row['student_id'], row['version'] - 1,
                    row['status'], str(row['score']) if row['score'] is not None else None, row['reason'])
        previous[student_key] = row
        counts[key] = counts.get(key, 0) + 1
    for key, exam in exams.items():
        CreateExam(exam['exam_id'], exam['class_id'], exam['term_id'], exam['title'], exam['subject'], str(exam['maximum_score']))
        if exam['version'] != counts.get(key, 0) + 1:
            raise ValueError('Exam revision count mismatch')
    for layout in connection.execute(text('SELECT * FROM class_os.class_seating')).mappings():
        CreateSeatLayout(layout['layout_id'], layout['class_id'], layout['term_id'], layout['rows'], layout['columns'])
        snapshots = {}
        for row in connection.execute(text('''SELECT * FROM class_os.seat_revision WHERE workspace_id=:w AND layout_id=:l
            ORDER BY version,row_index,column_index'''), {'w': layout['workspace_id'], 'l': layout['layout_id']}).mappings():
            if (row['row_index'] > layout['rows'] or row['column_index'] > layout['columns']
                    or not layout['created_at'] <= row['created_at'] <= layout['updated_at']):
                raise ValueError('Invalid seating position history')
            snapshots.setdefault(row['version'], []).append(row)
        if set(snapshots) != set(range(1, layout['version'] + 1)) or any(len(rows) != layout['rows'] * layout['columns'] for rows in snapshots.values()):
            raise ValueError('Incomplete seating snapshots')
