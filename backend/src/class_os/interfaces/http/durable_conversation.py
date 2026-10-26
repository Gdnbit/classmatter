"""Explicit synthetic D1 transport. Only QG/BCG; never repositories or SQL.

Default create_app/local/desktop R1 composition does not install these routes.
Persisting a human send and explicitly starting its run are separate POSTs.
GET/reconstruction is read-only apart from the existing trusted read audit.
"""
from contextlib import aclosing
from dataclasses import asdict
from datetime import datetime
import json
from typing import Literal
from uuid import UUID

import anyio
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, model_validator
from starlette.responses import JSONResponse, StreamingResponse

from class_os.domain.conversation_control import ClearConversation
from class_os.domain.conversation_interaction import ArchiveConversation
from .app import create_app
from .contracts import WireModel
from .roster import credentials, CommandStatusResponse


class Attribution(WireModel):
    origin: Literal["source-import", "local-owner"]
    created_by: UUID | None
    last_modified_by: UUID | None
    source_workspace_id: UUID | None
    source_owner_id: UUID | None
    source_version: int | None
    content_authority: Literal["assistant-unverified", "user-original", "domain-data"]


class ThreadItem(WireModel):
    thread_id: UUID
    title: str = Field(min_length=1, max_length=80)
    status: Literal["active", "archived", "cleared"]
    version: int = Field(strict=True, ge=1, le=2147483647)
    student_id: UUID | None
    updated_at: datetime
    attribution: Attribution


class ListingResponse(WireModel):
    schema_version: Literal["classmatter.conversation-list.v1"] = "classmatter.conversation-list.v1"
    data: list[ThreadItem] = Field(max_length=50)
    snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    next_offset: int | None = Field(default=None, strict=True, ge=50, lt=10000)


class MessageContent(WireModel):
    role: Literal["user", "assistant"]
    origin: Literal["user-original", "assistant-unverified"]
    text: str = Field(min_length=1, max_length=8000)

    @model_validator(mode="after")
    def visible_value(self):
        from class_os.domain.durable_conversation import VisibleMessage
        VisibleMessage(self.role, self.origin, self.text)
        return self


class MessageView(WireModel):
    message_id: UUID
    turn_id: UUID
    created_at: datetime
    content: MessageContent


class HistoryView(WireModel):
    thread_id: UUID
    title: str = Field(min_length=1, max_length=80)
    status: Literal["active", "archived", "cleared"]
    version: int = Field(strict=True, ge=1, le=2147483647)
    messages: list[MessageView] = Field(max_length=100)
    truncated: bool


class MessageAttribution(WireModel):
    message_id: UUID
    attribution: Attribution


class SourceView(WireModel):
    source_id: UUID
    source_workspace_id: UUID
    source_owner_id: UUID
    receipt_id: UUID
    projection_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of: datetime


class DraftView(WireModel):
    command: Literal["task.create"]
    task_id: UUID
    class_id: UUID
    term_id: UUID
    title: str = Field(min_length=1, max_length=80)
    student_id: None = None
    source_record_id: None = None
    due_at: None = None


class ResultContent(WireModel):
    text: str = Field(min_length=1, max_length=4000)
    sources: list[SourceView] = Field(max_length=2)
    draft: DraftView | None


class ResultView(WireModel):
    message_id: UUID
    result: ResultContent
    content_authority: Literal["assistant-unverified"]
    draft_status: Literal["uncommitted"]


class HistoryResponse(WireModel):
    schema_version: Literal["classmatter.conversation-history.v1"] = "classmatter.conversation-history.v1"
    history: HistoryView
    thread_attribution: Attribution
    message_attributions: list[MessageAttribution] = Field(max_length=100)
    results: list[ResultView] = Field(max_length=50)
    next_before: int | None = Field(default=None, strict=True, ge=1, le=10000)


class CreateBody(WireModel):
    thread_id: UUID
    request_id: UUID
    title: str = Field(min_length=1, max_length=80)
    student_id: UUID | None = None


class RenameBody(WireModel):
    request_id: UUID
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)
    title: str = Field(min_length=1, max_length=80)


class SendBody(WireModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=2000)
    mode: Literal["chat", "read", "draft"]


class EmptyBody(WireModel):
    pass


class VersionBody(WireModel):
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)


class RunStatus(WireModel):
    schema_version: Literal["classmatter.conversation-run.v1"] = "classmatter.conversation-run.v1"
    run_id: UUID
    state: Literal["queued", "running", "cancel_requested", "completed", "failed", "cancelled", "interrupted", "unknown"]
    version: int = Field(strict=True, ge=1, le=2147483647)
    created_at: datetime
    queued_until: datetime
    ended_at: datetime | None


class ControlPayload(WireModel):
    command: Literal["conversation.clear", "conversation.archive"]
    thread_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)


class ControlStatus(WireModel):
    schema_version: Literal["classmatter.conversation-control.v1"] = "classmatter.conversation-control.v1"
    status: Literal["read-status-required"] = "read-status-required"


class ControlPreview(WireModel):
    schema_version: Literal["classmatter.conversation-preview.v1"] = "classmatter.conversation-preview.v1"
    proposal_id: UUID
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    risk: Literal["W1", "X"]
    expires_at: datetime
    payload: ControlPayload


def create_durable_app(settings, *, worker, query, sdk, readiness=None):
    # Exact scoped runtime validates Gateway/store/identity composition. This is
    # an opt-in trusted factory, not a request-controlled capability selector.
    from class_os.infrastructure.durable_agent import DurableChatRuntime
    runtime = DurableChatRuntime(worker, query, sdk)
    app = create_app(settings, identity=worker.identity, business=worker, query=query, readiness=readiness)
    app.include_router(router(runtime))
    return app


def router(runtime):
    from class_os.infrastructure.durable_agent import DurableChatRuntime
    if type(runtime) is not DurableChatRuntime:
        raise ValueError("Exact durable runtime required")
    routes = APIRouter(prefix="/api/workspaces/{workspace_id}/conversation-d1/classes/{class_id}/terms/{term_id}")
    worker, query = runtime.worker, runtime.query

    def listing(auth, class_id, term_id, snapshot=None, offset=0):
        page = query.conversation_listing(*auth, class_id, term_id, snapshot=snapshot, offset=offset)
        return {"data": page.items, "snapshot": page.snapshot, "next_offset": page.next_offset}

    @routes.get("/conversations", response_model=ListingResponse)
    def conversations(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request):
        return listing(credentials(request, workspace_id), class_id, term_id)

    @routes.get("/conversations/pages/{snapshot}/{offset}", response_model=ListingResponse)
    def conversation_page(workspace_id: UUID, class_id: UUID, term_id: UUID, snapshot: str, offset: int, request: Request):
        return listing(credentials(request, workspace_id), class_id, term_id, snapshot, offset)

    @routes.post("/conversations", response_model=CommandStatusResponse)
    def create(workspace_id: UUID, class_id: UUID, term_id: UUID, request: Request, body: CreateBody):
        return worker.create_conversation(*credentials(request, workspace_id, write=True), class_id, term_id,
            body.thread_id, body.request_id, body.title, body.student_id)

    @routes.post("/conversations/{thread_id}/rename", response_model=CommandStatusResponse)
    def rename(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, request: Request, body: RenameBody):
        return worker.rename_conversation(*credentials(request, workspace_id, write=True), class_id, term_id,
            thread_id, body.request_id, body.expected_version, body.title)

    def history(auth, class_id, term_id, thread_id, *, before=None, version=None):
        page = query.conversation_page(*auth, class_id, term_id, thread_id, before_ordinal=before, expected_version=version)
        return {**asdict(page.value), "next_before": page.next_before}

    @routes.get("/conversations/{thread_id}", response_model=HistoryResponse)
    def read(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, request: Request):
        return history(credentials(request, workspace_id), class_id, term_id, thread_id)

    @routes.get("/conversations/{thread_id}/pages/{version}/{before}", response_model=HistoryResponse)
    def read_page(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, version: int, before: int, request: Request):
        return history(credentials(request, workspace_id), class_id, term_id, thread_id, before=before, version=version)

    @routes.post("/conversations/{thread_id}/turns", response_model=CommandStatusResponse)
    def enqueue(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, request: Request, body: SendBody):
        return worker.enqueue(*credentials(request, workspace_id, write=True), class_id, term_id, thread_id,
                              body.request_id, body.text, body.mode)

    @routes.get("/conversations/{thread_id}/turns/{request_id}", response_model=RunStatus)
    def status(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, request_id: UUID, request: Request):
        return query.turn_status(*credentials(request, workspace_id), class_id, term_id, thread_id, request_id)

    @routes.post("/conversations/{thread_id}/turns/{request_id}/events")
    async def events(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, request_id: UUID, request: Request, body: EmptyBody):
        if request.headers.get("last-event-id"):
            raise HTTPException(400)
        auth = credentials(request, workspace_id, write=True)
        # Authorize and resolve the already committed human request BEFORE SSE
        # headers. No GET, startup or reconnect implicitly starts this route.
        current = await anyio.to_thread.run_sync(lambda: query.turn_status(*auth, class_id, term_id, thread_id, request_id))
        async def stream():
            cursor = 0
            try:
                async with aclosing(runtime.stream_queued(auth, class_id, term_id, thread_id, request_id)) as source:
                    async for event in source:
                        cursor = event.cursor
                        payload = {"cursor": cursor, "run_id": str(event.run_id), "type": event.type, "payload": event.payload}
                        yield f"id: {cursor}\nevent: {event.type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception:
                payload = {"cursor": cursor + 1, "run_id": str(current["run_id"]), "type": "run.failed",
                           "payload": {"code": "run_or_delivery_unknown"}}
                yield f"id: {cursor + 1}\nevent: run.failed\ndata: {json.dumps(payload)}\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"x-accel-buffering": "no"})

    @routes.post("/conversations/{thread_id}/runs/{run_id}/cancel", response_model=ControlStatus)
    def cancel(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, run_id: UUID, request: Request, body: VersionBody):
        worker.cancel_run(credentials(request, workspace_id, write=True), class_id, term_id, thread_id, run_id, body.expected_version)
        return {"schema_version": "classmatter.conversation-control.v1", "status": "read-status-required"}

    @routes.post("/conversations/{thread_id}/runs/{run_id}/reconcile", response_model=ControlStatus)
    def reconcile(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, run_id: UUID, request: Request, body: EmptyBody):
        worker.reconcile_run(credentials(request, workspace_id, write=True), class_id, term_id, thread_id, run_id)
        return {"schema_version": "classmatter.conversation-control.v1", "status": "read-status-required"}

    def preview(auth, command):
        result = worker.preview(*auth, command)
        envelope = {"schema_version": "classmatter.conversation-preview.v1", "proposal_id": str(result.proposal_id),
                    "payload_hash": result.payload_hash, "risk": result.risk,
                    "expires_at": result.expires_at.isoformat(), "payload": result.command.canonical()}
        ControlPreview.model_validate(envelope)
        return JSONResponse(envelope)  # Preserve canonical hash primitives.

    @routes.post("/conversations/{thread_id}/clear/preview", response_model=ControlPreview)
    def clear_preview(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, request: Request, body: VersionBody):
        return preview(credentials(request, workspace_id, write=True), ClearConversation(thread_id, class_id, term_id, body.expected_version))

    @routes.post("/conversations/{thread_id}/archive/preview", response_model=ControlPreview)
    def archive_preview(workspace_id: UUID, class_id: UUID, term_id: UUID, thread_id: UUID, request: Request, body: VersionBody):
        return preview(credentials(request, workspace_id, write=True), ArchiveConversation(thread_id, class_id, term_id, body.expected_version))

    return routes
