"""Owner/workspace chat transport; human action previews delegate to original BCG."""
from contextlib import aclosing
from datetime import datetime
import json
from typing import Literal
from uuid import UUID

import anyio
from fastapi import APIRouter, Request, HTTPException
from pydantic import Field, model_validator
from starlette.responses import StreamingResponse

from class_os.application.roster import CommandRejected
from class_os.domain.workspace_chat import candidate
from class_os.domain.change_preview import ChangePreview
from .contracts import WireModel
from .roster import credentials, ClassBody, ClassChangeBody, TermBody, StudentBody, StudentNameBody, TaskBody, ChangeTaskBody
from .documents import DocumentCreate, DocumentRevise
from .classroom_work import ExamCreate, ScoreRecord, SeatLayoutCreate, SeatAssign, SeatSwap


class ClassEditCandidate(ClassChangeBody):
    command: Literal["class.update"]


class TaskEditCandidate(ChangeTaskBody):
    command: Literal["task.update"]


Candidate = ClassBody | ClassEditCandidate | TermBody | StudentBody | StudentNameBody | TaskBody | TaskEditCandidate | DocumentCreate | DocumentRevise | ExamCreate | ScoreRecord | SeatLayoutCreate | SeatAssign | SeatSwap


class ChatCapabilities(WireModel):
    schema_version: Literal["classmatter.workspace-chat-capabilities.v1"] = "classmatter.workspace-chat-capabilities.v1"
    profile: Literal["workspace-chat-d3"] = "workspace-chat-d3"
    memory: Literal["persisted-not-fact"] = "persisted-not-fact"
    class_required: Literal[False] = False
    agent_business_write: Literal[False] = False
    complete_exit: Literal[False] = False


class ChatThread(WireModel):
    thread_id: UUID
    title: str = Field(min_length=1, max_length=80)
    status: Literal["active", "archived", "cleared"]
    version: int = Field(strict=True, ge=1)
    created_at: datetime
    updated_at: datetime
    cleared_at: datetime | None


class ChatActionReceipt(WireModel):
    receipt_id: UUID
    resource_id: UUID
    version: int = Field(strict=True, ge=1)


class ChatTurn(WireModel):
    turn_id: UUID
    request_id: UUID
    ordinal: int = Field(strict=True, ge=1, le=10000)
    state: Literal["queued", "running", "completed", "failed", "cancelled", "unknown"]
    version: int = Field(strict=True, ge=1)
    user_text: str | None = Field(max_length=2000)
    assistant_text: str | None = Field(max_length=4000)
    candidate: Candidate | None
    candidate_hash: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
    started_at: datetime | None
    lease_until: datetime | None
    ended_at: datetime | None
    input_tokens: int | None = Field(strict=True, ge=0)
    output_tokens: int | None = Field(strict=True, ge=0)
    duration_ms: int | None = Field(strict=True, ge=0)
    action_receipt: ChatActionReceipt | None
    change_preview: ChangePreview | None = None


def visible_turn(row):
    return ChatTurn(**{key: row.get(key) for key in ChatTurn.model_fields})


class ChatListing(WireModel):
    schema_version: Literal["classmatter.workspace-chat-list.v1"] = "classmatter.workspace-chat-list.v1"
    data: list[ChatThread] = Field(max_length=50)
    next_offset: int | None = Field(strict=True, ge=50, lt=10000)


class ChatHistory(WireModel):
    schema_version: Literal["classmatter.workspace-chat-history.v1"] = "classmatter.workspace-chat-history.v1"
    thread: ChatThread
    turns: list[ChatTurn] = Field(max_length=20)
    next_before: int | None = Field(strict=True, ge=1, le=10000)


class ChatTurnResponse(WireModel):
    schema_version: Literal["classmatter.workspace-chat-turn.v1"] = "classmatter.workspace-chat-turn.v1"
    turn: ChatTurn


class ChatSend(WireModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=2000)


class ChatEmpty(WireModel):
    pass


class ChatVersion(WireModel):
    expected_version: int = Field(strict=True, ge=1, lt=2147483647)


class ChatClear(ChatVersion):
    confirm_clear: Literal[True]


class ChatThreadResponse(WireModel):
    schema_version: Literal["classmatter.workspace-chat-thread.v1"] = "classmatter.workspace-chat-thread.v1"
    thread: ChatThread


class CandidatePreviewBody(WireModel):
    candidate_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CandidatePreview(WireModel):
    schema_version: Literal["classmatter.workspace-chat-preview.v1"] = "classmatter.workspace-chat-preview.v1"
    proposal_id: UUID
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    risk: Literal["W1", "W2"]
    expires_at: datetime
    payload: Candidate
    change_preview: ChangePreview | None = None


def router(runtime, commands):
    routes = APIRouter(prefix="/api/workspaces/{workspace_id}/workspace-chat")

    @routes.get("/capabilities", response_model=ChatCapabilities)
    def capabilities(workspace_id: UUID, request: Request):
        runtime.query.listing(credentials(request, workspace_id, write=False))
        return ChatCapabilities()

    @routes.get("/threads", response_model=ChatListing)
    def listing(workspace_id: UUID, request: Request):
        return ChatListing(**runtime.query.listing(credentials(request, workspace_id, write=False)))

    @routes.get("/threads/pages/{offset}", response_model=ChatListing)
    def listing_page(workspace_id: UUID, offset: int, request: Request):
        return ChatListing(**runtime.query.listing(credentials(request, workspace_id, write=False), offset=offset))

    @routes.get("/threads/{thread_id}", response_model=ChatHistory)
    def history(workspace_id: UUID, thread_id: UUID, request: Request):
        data = runtime.query.history(credentials(request, workspace_id, write=False), thread_id)
        return ChatHistory(**{**data, "turns": [visible_turn(row) for row in data["turns"]]})

    @routes.get("/threads/{thread_id}/before/{before}", response_model=ChatHistory)
    def history_page(workspace_id: UUID, thread_id: UUID, before: int, request: Request):
        data = runtime.query.history(credentials(request, workspace_id, write=False), thread_id, before=before)
        return ChatHistory(**{**data, "turns": [visible_turn(row) for row in data["turns"]]})

    @routes.post("/threads/{thread_id}/turns", response_model=ChatTurnResponse)
    def send(workspace_id: UUID, thread_id: UUID, request: Request, body: ChatSend):
        row = runtime.business.send(credentials(request, workspace_id, write=True), thread_id, body.request_id, body.text)
        return ChatTurnResponse(turn=visible_turn(row))

    @routes.post("/threads/{thread_id}/turns/{request_id}/events")
    async def events(workspace_id: UUID, thread_id: UUID, request_id: UUID, request: Request, body: ChatEmpty):
        if request.headers.get("last-event-id"):
            raise HTTPException(400)
        options = request.headers.getlist('x-classmatter-reasoning')
        if len(options) > 1 or options and options[0] not in ('low', 'medium', 'high'):
            raise HTTPException(400)
        reasoning = options[0] if options else None
        auth = credentials(request, workspace_id, write=True)
        await anyio.to_thread.run_sync(lambda: runtime.query.history(auth, thread_id))
        async def stream():
            async with aclosing(runtime.stream_queued(auth, thread_id, request_id, reasoning=reasoning)) as source:
                async for event in source:
                    data = {"cursor": event.cursor, "run_id": str(event.run_id), "type": event.type, "payload": event.payload}
                    yield f"id: {event.cursor}\nevent: {event.type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"x-accel-buffering": "no"})

    @routes.post("/threads/{thread_id}/turns/{request_id}/cancel", response_model=ChatTurnResponse)
    def cancel(workspace_id: UUID, thread_id: UUID, request_id: UUID, request: Request, body: ChatVersion):
        row = runtime.business.cancel(credentials(request, workspace_id, write=True), thread_id, request_id, body.expected_version)
        return ChatTurnResponse(turn=visible_turn(row))

    @routes.post("/threads/{thread_id}/clear", response_model=ChatThreadResponse)
    def clear(workspace_id: UUID, thread_id: UUID, request: Request, body: ChatClear):
        row = runtime.business.control(credentials(request, workspace_id, write=True), thread_id, body.expected_version, "clear")
        return ChatThreadResponse(thread=ChatThread(**row))

    @routes.post("/threads/{thread_id}/archive", response_model=ChatThreadResponse)
    def archive(workspace_id: UUID, thread_id: UUID, request: Request, body: ChatVersion):
        row = runtime.business.control(credentials(request, workspace_id, write=True), thread_id, body.expected_version, "archive")
        return ChatThreadResponse(thread=ChatThread(**row))

    @routes.post("/threads/{thread_id}/turns/{request_id}/proposal", response_model=CandidatePreview)
    def preview(workspace_id: UUID, thread_id: UUID, request_id: UUID, request: Request, body: CandidatePreviewBody):
        auth = credentials(request, workspace_id, write=True)
        header, row = runtime.query.turn(auth, thread_id, request_id)
        if header["status"] != "active" or row["state"] != "completed" or row["candidate"] is None or row["candidate_hash"] != body.candidate_hash or row["action_receipt"] is not None:
            raise CommandRejected()
        command = candidate(row["candidate"])
        # Trusted human adapter, not an Agent tool. Original BCG validates
        # scope/version/risk and creates the original approval/commit proposal.
        result = commands.preview(*auth, command)
        if row.get('change_preview') is None and commands.store.database.profile == 'classroom-work-d4':
            header, row = runtime.query.turn(auth, thread_id, request_id)
            if header['status'] != 'active' or row.get('change_preview') is None:
                raise CommandRejected()
        return CandidatePreview(proposal_id=result.proposal_id, payload_hash=result.payload_hash,
            risk=result.risk, expires_at=result.expires_at, payload=result.command.canonical(), change_preview=row.get('change_preview'))
    return routes


def create_workspace_chat_app(settings, *, worker, query, sdk, readiness=None, model_controller=None):
    from .workbench import create_workbench_app
    from class_os.application.workbench import WorkbenchBusinessGateway, WorkbenchQueryGateway
    from class_os.application.workspace_chat import WorkspaceChatBusinessGateway, WorkspaceChatQueryGateway
    from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
    if (type(worker) is not WorkbenchBusinessGateway or type(query) is not WorkbenchQueryGateway
            or worker.store.database.profile not in ("workspace-chat-d3", "classroom-work-d4")):
        raise ValueError("Explicit workspace chat assembly required")
    app = create_workbench_app(settings, worker=worker, query=query, sdk=sdk, readiness=readiness, model_controller=model_controller)
    business = WorkspaceChatBusinessGateway(worker.identity, worker.store, clock=worker.clock)
    history = WorkspaceChatQueryGateway(query.identity, query.store, clock=query.clock)
    runtime = WorkspaceChatRuntime(business, history, sdk)
    app.include_router(router(runtime, worker))
    if worker.store.database.profile == 'classroom-work-d4':
        from .classroom_work import router as classroom_router
        app.include_router(classroom_router(worker, query))
        from .composer import router as composer_router
        app.state.composer_capture_enabled = True
        app.include_router(composer_router(query, model_controller))
    return app
