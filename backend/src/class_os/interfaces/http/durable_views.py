"""Closed author-aware D1 projections; frozen R1 wire models stay unchanged."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field

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


def router(query):
    from class_os.application.conversation_interaction import ConversationInteractionQuery
    if type(query) is not ConversationInteractionQuery:
        raise ValueError("Exact attributed D1 query required")
    routes = APIRouter(prefix="/api/workspaces/{workspace_id}/conversation-d1")

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
