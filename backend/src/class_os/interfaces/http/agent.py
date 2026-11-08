"""Cookie/CSRF SSE adapter. Cannot approve/commit or access repositories."""
from contextlib import aclosing
from datetime import datetime
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field
from starlette.responses import StreamingResponse

from class_os.application.agent import AgentRequest, AgentRejected, Mode, DraftKind
from .contracts import WireModel
from .roster import credentials


class ConversationBody(WireModel):
    pass


class WorkspaceConversationBody(WireModel):
    schema_version: Literal["classmatter.workspace-conversation-request.v1"]


class WorkspaceConversationResponse(WireModel):
    schema_version: Literal["classmatter.workspace-conversation.v1"] = "classmatter.workspace-conversation.v1"
    conversation_id: UUID
    expires_at: datetime
    memory: Literal["ephemeral-not-fact"] = "ephemeral-not-fact"
    scope: Literal["workspace"] = "workspace"


class ScopedConversationBody(WireModel):
    schema_version: Literal["class-os.agent-conversation-request.v2"]
    student_id: UUID | None


class ScopedConversationResponse(WireModel):
    schema_version: Literal["class-os.agent-conversation.v2"]
    conversation_id: UUID
    expires_at: datetime
    memory: Literal["ephemeral-not-fact"]
    class_id: UUID
    term_id: UUID
    student_id: UUID | None


class TurnBody(WireModel):
    conversation_id: UUID
    text: str = Field(min_length=1, max_length=2000)
    mode: Mode


class RecordNoteTurnBody(WireModel):
    schema_version: Literal["class-os.agent-record-note-request.v1"]
    conversation_id: UUID
    text: str = Field(min_length=1, max_length=2000)


class RecordNoteCandidateResponse(WireModel):
    schema_version: Literal["class-os.record-note-candidate.v1"]
    status: Literal["unverified-user-note"]
    note_quote: str = Field(min_length=1, max_length=1000)
    source_start: int = Field(ge=0, le=1999)
    source_end: int = Field(ge=1, le=2000)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ConversationResponse(WireModel):
    schema_version: Literal["class-os.agent.v1"] = "class-os.agent.v1"
    conversation_id: UUID
    expires_at: datetime
    memory: Literal["ephemeral-not-fact"] = "ephemeral-not-fact"


class QueryReceiptReference(WireModel):
    entity: Literal["query_receipt"] = "query_receipt"
    id: UUID
    version: Literal[1] = 1
    projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime


def router(runtime, *, workspace_only=False):
    routes = APIRouter(prefix="/api/workspaces/{workspace_id}/agent")

    @routes.post("/workspace-conversations", response_model=WorkspaceConversationResponse)
    async def workspace_conversation(workspace_id: UUID, request: Request, body: WorkspaceConversationBody):
        item = runtime.workspace_conversation(credentials(request, workspace_id, write=True))
        return WorkspaceConversationResponse(conversation_id=item.conversation_id, expires_at=item.expires_at)

    @routes.post("/conversations", response_model=ConversationResponse | ScopedConversationResponse)
    async def conversation(workspace_id: UUID, request: Request, body: ConversationBody | ScopedConversationBody):
        if workspace_only:
            raise HTTPException(404)
        auth = credentials(request, workspace_id, write=True)
        if isinstance(body, ScopedConversationBody):
            item = runtime.conversation(auth, student_id=body.student_id)
            return ScopedConversationResponse(schema_version="class-os.agent-conversation.v2", conversation_id=item.conversation_id,
                expires_at=item.expires_at, memory="ephemeral-not-fact", class_id=item.class_id, term_id=item.term_id, student_id=item.student_id)
        item = runtime.conversation(auth)
        return {"schema_version": "class-os.agent.v1", "conversation_id": str(item.conversation_id),
                "expires_at": item.expires_at.isoformat(), "memory": "ephemeral-not-fact"}

    def event_response(auth, turn):
        item = runtime.prepare(auth, turn)
        if workspace_only and (turn.mode is not Mode.CHAT or item.class_id is not None or item.term_id is not None):
            raise AgentRejected()

        async def stream():
            async with aclosing(runtime.stream(auth, turn)) as source:
                async for event in source:
                    envelope = {"cursor": event.cursor, "run_id": str(event.run_id), "type": event.type, "payload": event.payload}
                    yield f"id: {event.cursor}\nevent: {event.type}\ndata: {json.dumps(envelope, ensure_ascii=False)}\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"x-accel-buffering": "no"})

    @routes.post("/events")
    async def events(workspace_id: UUID, request: Request, body: TurnBody):
        if request.headers.get("last-event-id"):
            raise HTTPException(400)
        return event_response(credentials(request, workspace_id, write=True), AgentRequest(body.conversation_id, body.text, body.mode))

    @routes.post("/record-note/events")
    async def record_note_events(workspace_id: UUID, request: Request, body: RecordNoteTurnBody):
        if workspace_only:
            raise HTTPException(404)
        if request.headers.get("last-event-id"):
            raise HTTPException(400)
        return event_response(credentials(request, workspace_id, write=True),
                              AgentRequest(body.conversation_id, body.text, Mode.DRAFT, DraftKind.RECORD_NOTE))

    @routes.post("/conversations/{conversation_id}/forget")
    async def forget(workspace_id: UUID, conversation_id: UUID, request: Request, body: ConversationBody):
        auth = credentials(request, workspace_id, write=True)
        if workspace_only:
            item = runtime.prepare(auth, AgentRequest(conversation_id, "forget", Mode.CHAT))
            if item.class_id is not None or item.term_id is not None:
                raise AgentRejected()
        runtime.forget(auth, conversation_id)
        return {"schema_version": "class-os.agent.v1", "status": "forgotten"}
    return routes
