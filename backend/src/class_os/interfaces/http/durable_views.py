"""Closed author-aware D1 projections; frozen R1 wire models stay unchanged."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field
from starlette.responses import JSONResponse

from .contracts import WireModel
from .durable_conversation import Attribution
from .roster import RecordView, TaskView, AuditEntry, credentials


class DomainAttribution(Attribution):
    created_by: UUID
    last_modified_by: UUID
    content_authority: Literal["domain-data"]


class AttributedRecord(RecordView):
    attribution: DomainAttribution


class AttributedTask(TaskView):
    attribution: DomainAttribution


class ActivityData(WireModel):
    as_of: datetime
    records: list[AttributedRecord] = Field(max_length=10000)
    tasks: list[AttributedTask] = Field(max_length=10000)


class ActivityResponse(WireModel):
    schema_version: Literal["classmatter.activity.v1"] = "classmatter.activity.v1"
    data: ActivityData


R1AuditAction = AuditEntry.model_fields["action"].annotation


class DurableAuditEntry(AuditEntry):
    action: R1AuditAction | Literal["conversation.history", "exit.conversation.summary", "exit.conversation.download", "conversation.transfer.proof"]


class AuditResponse(WireModel):
    schema_version: Literal["classmatter.business-audit.v1"] = "classmatter.business-audit.v1"
    as_of: datetime
    entries: list[DurableAuditEntry] = Field(max_length=100)
    truncated: bool
    partial_history: Literal[True]


class CapabilitiesResponse(WireModel):
    schema_version: Literal["classmatter.runtime-capabilities.v1"] = "classmatter.runtime-capabilities.v1"
    profile: Literal["conversation-d1"]
    data_mode: Literal["synthetic-only"]
    history_protocol: Literal["classmatter.conversation-history.v2"]


class ExitSummary(WireModel):
    schema_version: Literal["classmatter.conversation-exit-summary.v1"] = "classmatter.conversation-exit-summary.v1"
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    restriction_epoch: int = Field(strict=True, ge=0, le=2147483647)
    activation_allowed: Literal[False] = False


class ExitBody(WireModel):
    export_id: UUID
    expected_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExitPayload(ExitBody):
    command: Literal["conversation_exit.create"]


class ExitPreview(WireModel):
    schema_version: Literal["classmatter.conversation-exit-preview.v1"] = "classmatter.conversation-exit-preview.v1"
    proposal_id: UUID
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    risk: Literal["X"]
    expires_at: datetime
    payload: ExitPayload


def router(query, worker):
    from class_os.application.conversation_interaction import ConversationInteractionQuery
    if type(query) is not ConversationInteractionQuery:
        raise ValueError("Exact attributed D1 query required")
    routes = APIRouter(prefix="/api/workspaces/{workspace_id}/conversation-d1")

    @routes.get("/exit/summary", response_model=ExitSummary)
    def exit_summary(workspace_id: UUID, request: Request):
        summary = query.conversation_exit_summary(*credentials(request, workspace_id))
        return {"snapshot_hash": summary.snapshot_hash, "restriction_epoch": summary.restriction_epoch}

    @routes.post("/exit/preview", response_model=ExitPreview)
    def exit_preview(workspace_id: UUID, request: Request, body: ExitBody):
        from class_os.domain.conversation_exit import CreateConversationExit
        proposal = worker.preview(*credentials(request, workspace_id, write=True),
            CreateConversationExit(body.export_id, body.expected_snapshot_hash))
        envelope = {"schema_version": "classmatter.conversation-exit-preview.v1",
            "proposal_id": str(proposal.proposal_id), "payload_hash": proposal.payload_hash,
            "risk": proposal.risk, "expires_at": proposal.expires_at.isoformat(), "payload": proposal.command.canonical()}
        ExitPreview.model_validate(envelope)
        return JSONResponse(envelope)

    @routes.get("/exit/{export_id}/download")
    def exit_download(workspace_id: UUID, export_id: UUID, request: Request):
        artifact = query.conversation_exit_download(*credentials(request, workspace_id), export_id)
        return JSONResponse(artifact.bundle, headers={"content-disposition":
            f'attachment; filename="classmatter-synthetic-conversation-{export_id}.json"'})

    @routes.get("/capabilities", response_model=CapabilitiesResponse)
    def capabilities(workspace_id: UUID, request: Request):
        return query.conversation_capabilities(*credentials(request, workspace_id))

    @routes.get("/classes/{class_id}/terms/{term_id}/activity", response_model=ActivityResponse)
    def activity(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return {"data": query.projection(*credentials(request, workspace_id), class_id, term_id)}

    @routes.get("/classes/{class_id}/terms/{term_id}/students/{student_id}/timeline", response_model=ActivityResponse)
    def timeline(workspace_id: UUID, class_id: UUID, term_id: UUID, student_id: UUID, request: Request):
        return {"data": query.projection(*credentials(request, workspace_id), class_id, term_id, student_id=student_id)}

    @routes.get("/classes/{class_id}/terms/{term_id}/audit", response_model=AuditResponse)
    def audit(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return query.audit_log(*credentials(request, workspace_id), class_id, term_id)

    return routes
