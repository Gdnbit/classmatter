"""Closed post-R1 exam/results and seating commands; no generic schema mutation."""
from dataclasses import dataclass
from decimal import Decimal
import re
from typing import ClassVar
from uuid import UUID

from .roster import identifiers, name
from .documents import version


def score_value(value):
    if type(value) is not str or not re.fullmatch(r'(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,2})?', value):
        raise ValueError('Score must be a bounded exact decimal string')
    return Decimal(value)


def coordinate(row, column):
    if any(type(value) is not int or not 1 <= value <= 20 for value in (row, column)):
        raise ValueError('Seat coordinate outside bounds')


class ClassroomCommand:
    operation: ClassVar[str]

    def canonical(self):
        return {'command': self.operation, **{key: str(value) if type(value) is UUID else value
            for key, value in self.__dict__.items()}}


@dataclass(frozen=True)
class CreateExam(ClassroomCommand):
    exam_id: UUID
    class_id: UUID
    term_id: UUID
    title: str
    subject: str
    maximum_score: str
    operation: ClassVar[str] = 'exam.create'

    def __post_init__(self):
        identifiers(self.exam_id, self.class_id, self.term_id)
        name(self.title); name(self.subject)
        if score_value(self.maximum_score) <= 0:
            raise ValueError('Positive maximum required')


@dataclass(frozen=True)
class RecordScore(ClassroomCommand):
    exam_id: UUID
    class_id: UUID
    term_id: UUID
    student_id: UUID
    expected_version: int
    status: str
    score: str | None
    reason: str = ''
    operation: ClassVar[str] = 'score.record'

    def __post_init__(self):
        identifiers(self.exam_id, self.class_id, self.term_id, self.student_id)
        if type(self.expected_version) is not int or not 0 <= self.expected_version < 2_147_483_647:
            raise ValueError('Invalid score version')
        if type(self.status) is not str or self.status not in ('scored', 'absent', 'exempt', 'not-recorded'):
            raise ValueError('Unsupported score status')
        if self.status == 'scored':
            score_value(self.score)
        elif self.score is not None:
            raise ValueError('Non-scored result must not contain a score')
        if type(self.reason) is not str or len(self.reason) > 500 or any(ord(char) < 32 for char in self.reason):
            raise ValueError('Invalid correction reason')
        if self.expected_version and not self.reason.strip():
            raise ValueError('Correction needs a reason')


@dataclass(frozen=True)
class CreateSeatLayout(ClassroomCommand):
    layout_id: UUID
    class_id: UUID
    term_id: UUID
    rows: int
    columns: int
    operation: ClassVar[str] = 'seat.layout.create'

    def __post_init__(self):
        identifiers(self.layout_id, self.class_id, self.term_id)
        coordinate(self.rows, self.columns)


@dataclass(frozen=True)
class AssignSeat(ClassroomCommand):
    layout_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    student_id: UUID
    row: int
    column: int
    operation: ClassVar[str] = 'seat.assign'

    def __post_init__(self):
        identifiers(self.layout_id, self.class_id, self.term_id, self.student_id)
        version(self.expected_version); coordinate(self.row, self.column)


@dataclass(frozen=True)
class SwapSeats(ClassroomCommand):
    layout_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    first_row: int
    first_column: int
    second_row: int
    second_column: int
    operation: ClassVar[str] = 'seat.swap'

    def __post_init__(self):
        identifiers(self.layout_id, self.class_id, self.term_id)
        version(self.expected_version)
        coordinate(self.first_row, self.first_column); coordinate(self.second_row, self.second_column)
        if (self.first_row, self.first_column) == (self.second_row, self.second_column):
            raise ValueError('Choose two distinct seats')


COMMAND_TYPES = (CreateExam, RecordScore, CreateSeatLayout, AssignSeat, SwapSeats)
COMMANDS = {value.operation: value for value in COMMAND_TYPES}


def decode_classroom(payload):
    if type(payload) is not dict or type(payload.get('command')) is not str or payload['command'] not in COMMANDS:
        raise ValueError('Closed classroom command required')
    cls = COMMANDS[payload['command']]
    fields = cls.__dataclass_fields__
    expected = {key for key in fields if key != 'operation'}
    if set(payload) != expected | {'command'}:
        raise ValueError('Unexpected classroom command fields')
    values = {key: UUID(value) if key.endswith('_id') and type(value) is str else value
              for key, value in payload.items() if key != 'command'}
    result = cls(**values)
    if result.canonical() != payload:
        raise ValueError('Noncanonical classroom command')
    return result
