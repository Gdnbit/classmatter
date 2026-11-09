"""Opt-in typed classroom pack; mutations delegate to the existing BCG."""
from datetime import datetime
from typing import Literal, Annotated
from uuid import UUID
from fastapi import APIRouter, Request
from pydantic import Field, model_validator
from class_os.domain.classroom_work import decode_classroom
from .contracts import WireModel
from .roster import credentials


class ClassroomScope(WireModel):
    class_id: UUID
    term_id: UUID


class ExamCreate(ClassroomScope):
    command: Literal['exam.create']
    exam_id: UUID
    title: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=80)
    maximum_score: str

    @model_validator(mode='after')
    def domain_valid(self):
        decode_classroom(self.model_dump(mode='json'))
        return self


class ScoreRecord(ClassroomScope):
    command: Literal['score.record']
    exam_id: UUID
    student_id: UUID
    expected_version: int = Field(strict=True, ge=0, lt=2147483647)
    status: Literal['scored', 'absent', 'exempt', 'not-recorded']
    score: str | None
    reason: str = Field(max_length=500)

    @model_validator(mode='after')
    def domain_valid(self):
        decode_classroom(self.model_dump(mode='json'))
        return self


class SeatLayoutCreate(ClassroomScope):
    command: Literal['seat.layout.create']
    layout_id: UUID
    rows: int = Field(strict=True, ge=1, le=20)
    columns: int = Field(strict=True, ge=1, le=20)


class SeatAssign(ClassroomScope):
    command: Literal['seat.assign']
    layout_id: UUID
    student_id: UUID
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)
    row: int = Field(strict=True, ge=1, le=20)
    column: int = Field(strict=True, ge=1, le=20)


class SeatSwap(ClassroomScope):
    command: Literal['seat.swap']
    layout_id: UUID
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)
    first_row: int = Field(strict=True, ge=1, le=20)
    first_column: int = Field(strict=True, ge=1, le=20)
    second_row: int = Field(strict=True, ge=1, le=20)
    second_column: int = Field(strict=True, ge=1, le=20)


ClassroomCommand = Annotated[ExamCreate | ScoreRecord | SeatLayoutCreate | SeatAssign | SeatSwap, Field(discriminator='command')]


class ClassroomCapabilities(WireModel):
    schema_version: Literal['classmatter.classroom-capabilities.v1'] = 'classmatter.classroom-capabilities.v1'
    profile: Literal['classroom-work-d4'] = 'classroom-work-d4'
    agent_business_write: Literal[False] = False
    complete_exit: Literal[False] = False


class ExamMetadata(WireModel):
    exam_id: UUID
    title: str
    subject: str
    maximum_score: str
    version: int = Field(strict=True, ge=1)


class ExamListing(WireModel):
    schema_version: Literal['classmatter.exams.v1'] = 'classmatter.exams.v1'
    exams: list[ExamMetadata] = Field(max_length=50)
    truncated: bool


class ScoreResult(WireModel):
    student_id: UUID
    version: int = Field(strict=True, ge=1)
    status: Literal['scored', 'absent', 'exempt', 'not-recorded']
    score: str | None
    reason: str
    created_at: datetime


class ExamResults(ExamMetadata):
    schema_version: Literal['classmatter.exam-results.v1'] = 'classmatter.exam-results.v1'
    results: list[ScoreResult]
    scored_count: int = Field(strict=True, ge=0)
    average: str | None


class SeatPosition(WireModel):
    row_index: int = Field(strict=True, ge=1, le=20)
    column_index: int = Field(strict=True, ge=1, le=20)
    student_id: UUID | None


class Seating(WireModel):
    layout_id: UUID
    rows: int = Field(strict=True, ge=1, le=20)
    columns: int = Field(strict=True, ge=1, le=20)
    version: int = Field(strict=True, ge=1)
    seats: list[SeatPosition] = Field(max_length=400)


class SeatingResponse(WireModel):
    schema_version: Literal['classmatter.seating.v1'] = 'classmatter.seating.v1'
    layout: Seating | None


class ClassroomPreview(WireModel):
    schema_version: Literal['classmatter.classroom-preview.v1'] = 'classmatter.classroom-preview.v1'
    proposal_id: UUID
    payload_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    risk: Literal['W2']
    expires_at: datetime
    payload: ExamCreate | ScoreRecord | SeatLayoutCreate | SeatAssign | SeatSwap


def router(business, query):
    if business.store is not query.store or business.store.database.profile != 'classroom-work-d4':
        raise ValueError('Explicit classroom pack required')
    routes = APIRouter(prefix='/api/workspaces/{workspace_id}')

    @routes.get('/classroom-work/capabilities', response_model=ClassroomCapabilities)
    def capabilities(workspace_id: UUID, request: Request):
        query.agent_workspace_context(*credentials(request, workspace_id))
        return ClassroomCapabilities()

    @routes.get('/classes/{class_id}/terms/{term_id}/exams', response_model=ExamListing)
    def listing(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return query.classroom_read(credentials(request, workspace_id), class_id, term_id)

    @routes.get('/classes/{class_id}/terms/{term_id}/exams/{exam_id}', response_model=ExamResults)
    def results(workspace_id: UUID, class_id: UUID, term_id: UUID, exam_id: UUID, request: Request):
        return query.classroom_read(credentials(request, workspace_id), class_id, term_id, exam_id=exam_id)

    @routes.get('/classes/{class_id}/terms/{term_id}/seating', response_model=SeatingResponse)
    def seating(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        value = query.classroom_read(credentials(request, workspace_id), class_id, term_id, seating=True)
        if value:
            value['seats'] = [{key: row[key] for key in ('row_index', 'column_index', 'student_id')} for row in value['seats']]
        return SeatingResponse(layout=value)

    @routes.post('/classroom-commands/preview', response_model=ClassroomPreview)
    def preview(workspace_id: UUID, request: Request, body: ClassroomCommand):
        result = business.preview(*credentials(request, workspace_id, write=True), decode_classroom(body.model_dump(mode='json')))
        return ClassroomPreview(proposal_id=result.proposal_id, payload_hash=result.payload_hash, risk=result.risk,
            expires_at=result.expires_at, payload=result.command.canonical())
    return routes
