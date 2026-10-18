"""Closed roster HTTP adapters; repository/SQL access is prohibited here."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, SecretStr
from starlette.responses import JSONResponse

from class_os.domain.roster import decode
from .contracts import WireModel
from .identity import mutation, value


class ClassBody(WireModel):
    command: Literal["class.create"]
    class_id: UUID
    term_id: UUID
    name: str = Field(min_length=1, max_length=80)
    term_name: str = Field(min_length=1, max_length=80)
    start_date: date
    end_date: date


class StudentBody(WireModel):
    command: Literal["student.create"]
    student_id: UUID
    class_id: UUID
    term_id: UUID
    expected_class_version: int = Field(strict=True, ge=1)
    name: str = Field(min_length=1, max_length=80)


class ClassChangeBody(WireModel):
    command: Literal["class.update", "class.archive"]
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1)
    name: str = Field(min_length=1, max_length=80)


class TermBody(WireModel):
    command: Literal["term.update"]
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)
    previous_name: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    previous_start_date: date
    start_date: date
    previous_end_date: date
    end_date: date


class StudentNameBody(WireModel):
    command: Literal["student.update_name"]
    student_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1)
    previous_name: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)


class DeactivateBody(WireModel):
    command: Literal["student.deactivate"]
    student_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1)


class IdentifierBody(WireModel):
    command: Literal["student.update_identifier"]
    identifier_id: UUID
    student_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1)
    authority: str = Field(min_length=1, max_length=80)
    identifier_type: Literal["school_number", "exam_number"]
    value: str = Field(min_length=1, max_length=80)
    valid_from: datetime
    valid_to: datetime | None = None
    supersedes_identifier_id: UUID | None = None


class RecordBody(WireModel):
    command: Literal["record.create"]
    record_id: UUID
    class_id: UUID
    term_id: UUID
    student_id: UUID
    kind: Literal["attendance_late_fact", "attendance_absent_fact", "leave_requested_fact", "leave_approved_fact",
                  "leave_returned_fact", "homework_missing_fact", "homework_submitted_fact", "ordinary_fact",
                  "teacher_observation", "discipline_fact", "conversation_fact"]
    occurred_at: datetime
    fact_text: str = Field(max_length=2000)
    observation_text: str = Field(max_length=2000)
    related_record_id: UUID | None = None


class ReviseBody(WireModel):
    command: Literal["record.correct", "record.supersede"]
    record_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1)
    fact_text: str = Field(max_length=2000)
    observation_text: str = Field(max_length=2000)
    reason: str = Field(min_length=1, max_length=500)


class TaskBody(WireModel):
    command: Literal["task.create"]
    task_id: UUID
    class_id: UUID
    term_id: UUID
    title: str = Field(min_length=1, max_length=80)
    due_at: datetime | None = None
    student_id: UUID | None = None
    source_record_id: UUID | None = None


class ChangeTaskBody(WireModel):
    command: Literal["task.update", "task.complete", "task.cancel"]
    task_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1)
    status: Literal["not-started", "in-progress", "waiting", "done", "cancelled"]
    evidence: str = Field(default="", max_length=500)
    title: str | None = Field(default=None, min_length=1, max_length=80)
    due_at: datetime | None = None
    change_due_date: bool = Field(default=False, strict=True)


class ExitBody(WireModel):
    command: Literal["exit_export.create"]
    export_id: UUID
    expected_core_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ModelControlBody(WireModel):
    command: Literal["model_configuration.save", "model_configuration.clear"]
    candidate_id: UUID
    expected_version: int = Field(strict=True, ge=0, lt=2147483647)
    protocol: Literal["chat-completions", "responses"] | None
    model: str | None = Field(max_length=128)
    base_url: str | None = Field(max_length=512)


CommandBody = Annotated[ClassBody | StudentBody | ClassChangeBody | TermBody | StudentNameBody | DeactivateBody | IdentifierBody |
                        RecordBody | ReviseBody | TaskBody | ChangeTaskBody | ExitBody | ModelControlBody, Field(discriminator="command")]


class ApprovalBody(WireModel):
    proposal_id: UUID
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProposalBody(WireModel):
    proposal_id: UUID


class CommitBody(ProposalBody):
    idempotency_key: UUID
    approval: SecretStr | None = Field(default=None, min_length=32, max_length=128)


class PreviewResponse(WireModel):
    schema_version: Literal["class-os.roster.v1"] = "class-os.roster.v1"
    proposal_id: UUID
    payload_hash: str
    risk: Literal["W1", "W2"]
    expires_at: datetime
    payload: CommandBody


class ReceiptResponse(WireModel):
    schema_version: Literal["class-os.roster.v1"] = "class-os.roster.v1"
    receipt_id: UUID
    resource_id: UUID
    version: int


class StatusReceipt(WireModel):
    receipt_id: UUID
    resource_id: UUID
    version: int = Field(strict=True, ge=1)


class CommandStatusResponse(WireModel):
    schema_version: Literal["class-os.command-status.v1"] = "class-os.command-status.v1"
    proposal_id: UUID
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["committed", "not_committed", "unavailable"]
    receipt: StatusReceipt | None


class StudentView(WireModel):
    student_id: UUID
    name: str
    version: int
    status: Literal["active", "inactive"] = "active"


class ClassView(WireModel):
    class_id: UUID
    term_id: UUID
    name: str
    term_name: str
    version: int


class TermMetadataResponse(WireModel):
    schema_version: Literal["class-os.term-metadata.v1"] = "class-os.term-metadata.v1"
    class_id: UUID
    term_id: UUID
    name: str = Field(min_length=1, max_length=80)
    start_date: date
    end_date: date
    version: int = Field(strict=True, ge=1, lt=2147483647)


class ContextResponse(WireModel):
    schema_version: Literal["class-os.roster.v1"] = "class-os.roster.v1"
    data: ClassView | None


class RosterResponse(WireModel):
    schema_version: Literal["class-os.roster.v1"] = "class-os.roster.v1"
    data: list[StudentView]


class HistoricalClass(ClassView):
    status: Literal["active", "archived"]


class HistoryResponse(WireModel):
    schema_version: Literal["class-os.roster.v1"] = "class-os.roster.v1"
    data: list[HistoricalClass]


class RecordView(WireModel):
    record_id: UUID
    version: int
    student_id: UUID
    kind: str
    occurred_at: datetime
    recorded_at: datetime
    fact_text: str
    observation_text: str
    source: Literal["trusted-ui-synthetic"]
    related_record_id: UUID | None
    revision_kind: Literal["create", "correct", "supersede"]
    revision_reason: str


class TaskView(WireModel):
    task_id: UUID
    title: str
    student_id: UUID | None
    source_record_id: UUID | None
    due_at: datetime | None
    status: Literal["not-started", "in-progress", "waiting", "done", "cancelled"]
    evidence: str
    version: int
    overdue: bool


class ActivityData(WireModel):
    as_of: datetime
    records: list[RecordView]
    tasks: list[TaskView]


class ActivityResponse(WireModel):
    schema_version: Literal["class-os.activity.v1"] = "class-os.activity.v1"
    data: ActivityData


class AuditEntry(WireModel):
    event_id: UUID
    action: Literal["command.preview", "command.approve", "command.reject", "command.commit", "command.status", "roster.list", "class.context",
                    "class.history", "identifier.list", "duplicate.list", "activity.today", "student.timeline",
                    "agent.run.started", "agent.run.completed", "agent.run.failed", "agent.run.cancelled", "exit.summary", "exit.download", "audit.list",
                    "model.config.read", "model.test.started", "model.test.completed", "model.test.failed", "model.enable", "model.disable", "model.invoke"]
    outcome: Literal["allowed", "denied"]
    occurred_at: datetime
    proposal_id: UUID | None
    payload_hash: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_id: UUID | None
    resource_id: UUID | None
    resource_version: int | None = Field(strict=True, ge=1)


class AuditResponse(WireModel):
    schema_version: Literal["class-os.business-audit.v1"] = "class-os.business-audit.v1"
    as_of: datetime
    entries: list[AuditEntry] = Field(max_length=100)
    truncated: bool
    partial_history: Literal[True]


class IdentifierView(WireModel):
    identifier_id: UUID
    student_id: UUID
    authority: str
    identifier_type: Literal["school_number", "exam_number"]
    value: str
    valid_from: datetime
    valid_to: datetime | None


class IdentifierResponse(WireModel):
    schema_version: Literal["class-os.roster.v1"] = "class-os.roster.v1"
    data: list[IdentifierView]


class DuplicateView(WireModel):
    left_student_id: UUID
    right_student_id: UUID
    reason: Literal["identifier_conflict"]


class DuplicateResponse(WireModel):
    schema_version: Literal["class-os.roster.v1"] = "class-os.roster.v1"
    data: list[DuplicateView]


def credentials(request, workspace_id, *, write=False):
    csrf = mutation(request, "csrf") if write else value(request, "csrf")
    return value(request, "session"), value(request, "client"), csrf, workspace_id


def router(business, query):
    routes = APIRouter(prefix="/api/workspaces/{workspace_id}")

    @routes.post("/commands/preview", response_model=PreviewResponse)
    def preview(workspace_id: UUID, request: Request, body: CommandBody):
        auth = credentials(request, workspace_id, write=True)
        try:
            command = decode(body.model_dump(mode="json"))
        except ValueError:
            raise HTTPException(400) from None
        result = business.preview(*auth, command)
        envelope = {"schema_version": "class-os.roster.v1", "proposal_id": str(result.proposal_id),
                    "payload_hash": result.payload_hash, "risk": result.risk,
                    "expires_at": result.expires_at.isoformat(), "payload": result.command.canonical()}
        PreviewResponse.model_validate(envelope)
        # Keep the exact canonical primitives: response-model serialization
        # would insert optional defaults and normalize UTC strings to Z,
        # changing the hash input shown to the approving human/client.
        return JSONResponse(envelope)

    @routes.post("/commands/approve")
    def approve(workspace_id: UUID, request: Request, body: ApprovalBody):
        capability = business.approve(*credentials(request, workspace_id, write=True), body.proposal_id, body.payload_hash)
        return {"schema_version": "class-os.roster.v1", "approval": capability}

    @routes.post("/commands/reject")
    def reject(workspace_id: UUID, request: Request, body: ProposalBody):
        business.reject(*credentials(request, workspace_id, write=True), body.proposal_id)
        return {"schema_version": "class-os.roster.v1", "status": "rejected"}

    @routes.get("/commands/{proposal_id}/receipts/{key}", response_model=CommandStatusResponse)
    def command_status(workspace_id: UUID, proposal_id: UUID, key: UUID, request: Request):
        return query.command_status(*credentials(request, workspace_id), proposal_id, key)

    @routes.post("/commands/commit", response_model=ReceiptResponse)
    def commit(workspace_id: UUID, request: Request, body: CommitBody):
        return business.commit(*credentials(request, workspace_id, write=True), body.proposal_id, body.idempotency_key,
                               body.approval.get_secret_value() if body.approval else None)

    @routes.get("/context", response_model=ContextResponse)
    def context(workspace_id: UUID, request: Request):
        return {"schema_version": "class-os.roster.v1", "data": query.context(*credentials(request, workspace_id))}

    @routes.get("/classes/{class_id}/terms/{term_id}/metadata", response_model=TermMetadataResponse)
    def term_metadata(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return query.term_metadata(*credentials(request, workspace_id), class_id, term_id)

    @routes.get("/exit/summary")
    def exit_summary(workspace_id: UUID, request: Request):
        summary = query.exit_summary(*credentials(request, workspace_id))
        return {"schema_version": "class-os.exit-summary.v1", "core_hash": summary.core_hash, "counts": summary.counts,
                "profile": "synthetic-core-only", "lifecycle_complete": False}

    @routes.get("/exit/{export_id}/download")
    def exit_download(workspace_id: UUID, export_id: UUID, request: Request):
        artifact = query.exit_download(*credentials(request, workspace_id), export_id)
        return JSONResponse(artifact.bundle, headers={"content-disposition": f'attachment; filename="class-os-core-{export_id}.json"'})

    @routes.get("/classes/{class_id}/terms/{term_id}/students", response_model=RosterResponse)
    def students(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return {"schema_version": "class-os.roster.v1", "data": query.roster(*credentials(request, workspace_id), class_id, term_id)}

    @routes.get("/classes", response_model=HistoryResponse)
    def history(workspace_id: UUID, request: Request):
        return {"data": query.history(*credentials(request, workspace_id))}

    @routes.get("/classes/{class_id}/terms/{term_id}/activity", response_model=ActivityResponse)
    def activity(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return {"data": query.projection(*credentials(request, workspace_id), class_id, term_id)}

    @routes.get("/classes/{class_id}/terms/{term_id}/audit", response_model=AuditResponse)
    def audit_log(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return query.audit_log(*credentials(request, workspace_id), class_id, term_id)

    @routes.get("/classes/{class_id}/terms/{term_id}/students/{student_id}/timeline", response_model=ActivityResponse)
    def timeline(workspace_id: UUID, class_id: UUID, term_id: UUID, student_id: UUID, request: Request):
        return {"data": query.projection(*credentials(request, workspace_id), class_id, term_id, student_id=student_id)}

    @routes.get("/classes/{class_id}/terms/{term_id}/identifiers", response_model=IdentifierResponse)
    def identifiers(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return {"data": query.projection(*credentials(request, workspace_id), class_id, term_id, view="identifiers")}

    @routes.get("/classes/{class_id}/terms/{term_id}/duplicates", response_model=DuplicateResponse)
    def duplicates(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return {"data": query.projection(*credentials(request, workspace_id), class_id, term_id, view="duplicates")}

    return routes
