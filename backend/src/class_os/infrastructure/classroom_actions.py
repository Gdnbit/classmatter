"""Closed classroom read/candidate tools; no command executor or SQL exposed."""
from typing import Literal
from uuid import uuid4
import re
from class_os.domain.classroom_work import CreateExam, RecordScore, CreateSeatLayout, AssignSeat, SwapSeats


def tools(capture, query, credentials, context, execute, missing_class):
    def exams(current, title, subject):
        listing = query.classroom_read(credentials, current.class_id, current.term_id)
        return [row for row in listing['exams'] if row['title'] == title and row['subject'] == subject]

    def students(current, name):
        return [row for row in query.roster(*credentials, current.class_id, current.term_id) if row.name == name and row.status == 'active']

    def explicit_number(value):
        return any(value in re.findall(r'(?<![0-9.])[0-9]+(?:\.[0-9]+)?(?![0-9.])', message) for message in capture.user_messages)

    needs = {'status': 'needs-information', 'instruction': 'Ask for missing or ambiguous exam/subject/student/score/seat information. Never guess, infer a score, or silently replace an occupied seat.'}

    async def read_classroom_work(kind: Literal['exams', 'scores', 'seating'], exam_title: str = '', subject: str = '') -> dict:
        """Read authorized current exams, exact score/status results or the seating layout. Resolve one exact exam title and subject for scores; never writes."""
        def read():
            current = context()
            if current is None:
                return missing_class
            if kind == 'exams':
                return query.classroom_read(credentials, current.class_id, current.term_id)
            if kind == 'seating':
                return {'layout': query.classroom_read(credentials, current.class_id, current.term_id, seating=True)}
            matches = exams(current, exam_title, subject)
            if len(matches) != 1:
                return needs
            data = query.classroom_read(credentials, current.class_id, current.term_id, exam_id=matches[0]['exam_id'])
            names = {row.student_id: row.name for row in query.roster(*credentials, current.class_id, current.term_id)}
            data['results'] = [{**row, 'student_name': names.get(row['student_id'], '未在当前名单中')} for row in data['results']]
            return data
        return await execute('read_classroom_work', read)

    async def prepare_exam(title: str, subject: str, maximum_score: str) -> dict:
        """Prepare one exam/subject with the explicitly supplied title, subject and full mark. Ask for missing full mark; never saves."""
        def prepare():
            current = context()
            if current is None:
                return missing_class
            if not capture.mentioned(title) or not capture.mentioned(subject) or not explicit_number(maximum_score):
                return needs
            if exams(current, title, subject):
                return {'status': 'existing-exam', 'instruction': 'Reuse the existing exam and subject; do not create a duplicate.'}
            return capture.propose(CreateExam(uuid4(), current.class_id, current.term_id, title, subject, maximum_score))
        return await execute('prepare_exam', prepare)

    async def prepare_score(exam_title: str, subject: str, student_name: str,
                            status: Literal['scored', 'absent', 'exempt', 'not-recorded'], score: str | None = None, reason: str = '') -> dict:
        """Prepare one explicitly provided student score or absence/exemption status in an exact exam/subject. Read current version, preserve correction history, never infer marks or save."""
        def prepare():
            current = context()
            if current is None:
                return missing_class
            matches, people = exams(current, exam_title, subject), students(current, student_name)
            if (len(matches) != 1 or len(people) != 1 or not all(capture.mentioned(value) for value in (exam_title, subject, student_name))
                    or status == 'scored' and not explicit_number(score)
                    or status != 'scored' and not capture.mentioned({'absent': '缺考', 'exempt': '免考', 'not-recorded': '未录入'}[status])):
                return needs
            data = query.classroom_read(credentials, current.class_id, current.term_id, exam_id=matches[0]['exam_id'])
            previous = next((row for row in data['results'] if row['student_id'] == people[0].student_id), None)
            if previous and (not reason.strip() or not capture.mentioned(reason)):
                return {'status': 'needs-correction-reason', 'instruction': 'Ask for the correction reason; keep the old result and never invent the reason.'}
            return capture.propose(RecordScore(matches[0]['exam_id'], current.class_id, current.term_id, people[0].student_id,
                previous['version'] if previous else 0, status, score, reason))
        return await execute('prepare_score', prepare)

    async def prepare_seat_layout(rows: int, columns: int) -> dict:
        """Prepare an empty seating layout using explicitly supplied row and column counts. Never guesses assignments or saves."""
        def prepare():
            current = context()
            if current is None:
                return missing_class
            if not explicit_number(str(rows)) or not explicit_number(str(columns)):
                return needs
            if query.classroom_read(credentials, current.class_id, current.term_id, seating=True) is not None:
                return {'status': 'existing-layout', 'instruction': 'Reuse the current seating layout; do not overwrite it.'}
            return capture.propose(CreateSeatLayout(uuid4(), current.class_id, current.term_id, rows, columns))
        return await execute('prepare_seat_layout', prepare)

    async def prepare_seat_assignment(student_name: str, row: int, column: int) -> dict:
        """Prepare moving one uniquely named student to an explicitly requested empty seat using the current layout version. Never displaces another student or saves."""
        def prepare():
            current = context()
            if current is None:
                return missing_class
            people = students(current, student_name)
            layout = query.classroom_read(credentials, current.class_id, current.term_id, seating=True)
            if len(people) != 1 or layout is None or not capture.mentioned(student_name) or not explicit_number(str(row)) or not explicit_number(str(column)):
                return needs
            cell = next((cell for cell in layout['seats'] if (cell['row_index'], cell['column_index']) == (row, column)), None)
            if cell is None or cell['student_id'] is not None:
                return needs
            return capture.propose(AssignSeat(layout['layout_id'], current.class_id, current.term_id, layout['version'], people[0].student_id, row, column))
        return await execute('prepare_seat_assignment', prepare)

    async def prepare_seat_swap(first_student: str, second_student: str) -> dict:
        """Prepare swapping the current seats of two explicitly named, unique active students. Read the actual layout, ask if either has no seat, never saves."""
        def prepare():
            current = context()
            if current is None:
                return missing_class
            left, right = students(current, first_student), students(current, second_student)
            layout = query.classroom_read(credentials, current.class_id, current.term_id, seating=True)
            if len(left) != 1 or len(right) != 1 or layout is None or not capture.mentioned(first_student) or not capture.mentioned(second_student):
                return needs
            first = next((cell for cell in layout['seats'] if cell['student_id'] == left[0].student_id), None)
            second = next((cell for cell in layout['seats'] if cell['student_id'] == right[0].student_id), None)
            if first is None or second is None or left[0].student_id == right[0].student_id:
                return needs
            return capture.propose(SwapSeats(layout['layout_id'], current.class_id, current.term_id, layout['version'],
                first['row_index'], first['column_index'], second['row_index'], second['column_index']))
        return await execute('prepare_seat_swap', prepare)

    return read_classroom_work, prepare_exam, prepare_score, prepare_seat_layout, prepare_seat_assignment, prepare_seat_swap
