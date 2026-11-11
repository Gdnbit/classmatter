"""Closed presentation contract. Never accepts commands, HTML or model-generated UI."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Presentation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class FieldChange(Presentation):
    field: Literal['name', 'term_name', 'start_date', 'end_date', 'title', 'due_at', 'status',
                   'student', 'source', 'body', 'format', 'subject', 'maximum_score', 'score', 'reason', 'evidence']
    before: str | None = Field(max_length=220000)
    after: str | None = Field(max_length=220000)


class SeatCell(Presentation):
    row: int = Field(ge=1, le=20)
    column: int = Field(ge=1, le=20)
    student: str | None = Field(max_length=80)
    student_id: str | None = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')


class SeatBoard(Presentation):
    rows: int = Field(ge=1, le=20)
    columns: int = Field(ge=1, le=20)
    cells: list[SeatCell] = Field(min_length=1, max_length=400)

    @model_validator(mode='after')
    def complete(self):
        if {(cell.row, cell.column) for cell in self.cells} != {
                (r, c) for r in range(1, self.rows + 1) for c in range(1, self.columns + 1)} or len(self.cells) != self.rows * self.columns:
            raise ValueError('Incomplete seating comparison')
        occupied = [cell.student_id for cell in self.cells if cell.student_id is not None]
        if len(occupied) != len(set(occupied)) or any((cell.student is None) != (cell.student_id is None) for cell in self.cells):
            raise ValueError('Invalid seating identities')
        return self


class ChangePreview(Presentation):
    schema_version: Literal['classmatter.change-preview.v1'] = 'classmatter.change-preview.v1'
    candidate_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    kind: Literal['create', 'edit', 'seating']
    fields: list[FieldChange] = Field(max_length=16)
    before_seats: SeatBoard | None
    after_seats: SeatBoard | None

    @model_validator(mode='after')
    def shape(self):
        if len({field.field for field in self.fields}) != len(self.fields):
            raise ValueError('Duplicate comparison fields')
        if self.kind == 'seating':
            if self.after_seats is None or self.fields:
                raise ValueError('Missing seating comparison')
        elif not self.fields or self.before_seats is not None or self.after_seats is not None:
            raise ValueError('Invalid field comparison')
        if self.kind == 'create' and any(field.before is not None for field in self.fields):
            raise ValueError('Creation cannot invent prior values')
        return self
