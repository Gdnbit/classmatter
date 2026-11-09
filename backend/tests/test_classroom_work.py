"""Exact grades and closed seating values; no database or model needed."""
from uuid import uuid4
import pytest

from class_os.domain.classroom_work import CreateExam, RecordScore, CreateSeatLayout, AssignSeat, SwapSeats, decode_classroom


def scope():
    return {'class_id': uuid4(), 'term_id': uuid4()}


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '1e2', '0.001', '01', 90, True])
def test_scores_reject_inexact_or_ambiguous_input(value):
    with pytest.raises(ValueError):
        CreateExam(uuid4(), **scope(), title='合成考试', subject='数学', maximum_score=value)


def test_zero_is_a_score_and_absence_is_not_zero():
    fields = dict(exam_id=uuid4(), **scope(), student_id=uuid4(), expected_version=0)
    zero = RecordScore(**fields, status='scored', score='0')
    assert decode_classroom(zero.canonical()) == zero
    absent = RecordScore(**fields, status='absent', score=None)
    assert decode_classroom(absent.canonical()) == absent
    with pytest.raises(ValueError):
        RecordScore(**fields, status='absent', score='0')
    with pytest.raises(ValueError):
        RecordScore(**{**fields, 'expected_version': 1}, status='scored', score='80')


def test_closed_payload_and_seat_coordinates():
    fields = scope()
    layout = CreateSeatLayout(uuid4(), **fields, rows=6, columns=6)
    assert decode_classroom(layout.canonical()) == layout
    assignment = AssignSeat(layout.layout_id, **fields, expected_version=1, student_id=uuid4(), row=1, column=2)
    assert decode_classroom(assignment.canonical()) == assignment
    with pytest.raises(ValueError):
        decode_classroom({**assignment.canonical(), 'sql': 'arbitrary'})
    for row in (0, 21, True):
        with pytest.raises(ValueError):
            CreateSeatLayout(uuid4(), **fields, rows=row, columns=6)
    with pytest.raises(ValueError):
        SwapSeats(layout.layout_id, **fields, expected_version=1, first_row=1, first_column=1, second_row=1, second_column=1)
