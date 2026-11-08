"""Workspace chat authenticates without a class; never grants domain tools."""
from uuid import uuid4
from pathlib import Path
import os
import socket
import subprocess
import threading
import time
import asyncio

import httpx
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text
import uvicorn

from class_os.application.agent import AgentRequest, AgentRejected, Mode
from class_os.application.identity import IdentityDenied
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_roster_gateway import roster, create_class
from test_identity import identity, PASSWORD
from test_conversation_control import control, storage


@pytest.mark.db
@pytest.mark.parametrize("fault", ["timeout", "audit", "tool"])
async def test_workspace_chat_faults_never_release_answers_or_gain_writes(roster, monkeypatch, fault):
    _, query, _, credentials, _, owner, _ = roster
    async def respond(messages, info):
        assert not info.function_tools
        if fault == "timeout":
            await asyncio.sleep(1)
        if fault == "tool":
            return ModelResponse(parts=[ToolCallPart("commands_commit", {"command": "class.create"})])
        return ModelResponse(parts=[TextPart("synthetic withheld answer")])
    runtime = PydanticAgentRuntime(query, model_factory=lambda _: FunctionModel(respond), timeout=.05 if fault == "timeout" else 10)
    conversation = runtime.workspace_conversation(credentials)
    if fault == "audit":
        original = query.agent_audit
        def audit(*args, **kwargs):
            if args[2] == "completed":
                raise RuntimeError("synthetic audit failure")
            return original(*args, **kwargs)
        monkeypatch.setattr(query, "agent_audit", audit)
    events = [event async for event in runtime.stream(credentials, AgentRequest(conversation.conversation_id, "synthetic request", Mode.CHAT))]
    assert events[-1].type == "run.failed"
    assert not any(event.type in ("message.delta", "draft.available", "run.completed") for event in events)
    assert not conversation.history and conversation.turns == 0 and runtime.active == 0
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.school_class")).scalar_one() == 0


@pytest.mark.db
async def test_workspace_chat_before_and_after_class_has_no_domain_tools(roster):
    business, query, _, credentials, _, owner, _ = roster
    seen = []
    def respond(messages, info):
        seen.append((len(messages), tuple(tool.name for tool in info.function_tools)))
        return ModelResponse(parts=[TextPart("synthetic ordinary response")])
    runtime = PydanticAgentRuntime(query, model_factory=lambda _: FunctionModel(respond))
    conversation = runtime.workspace_conversation(credentials)
    assert conversation.class_id is conversation.term_id is conversation.student_id is None
    for mode in (Mode.READ, Mode.DRAFT):
        with pytest.raises(AgentRejected):
            runtime.prepare(credentials, AgentRequest(conversation.conversation_id, "query or change a class", mode))
    for index in range(2):
        if index:
            create_class(business, credentials)
        events = [event async for event in runtime.stream(credentials, AgentRequest(conversation.conversation_id, "ordinary conversation", Mode.CHAT))]
        assert events[-1].type == "run.completed", runtime.last_failure_type
        assert not any(event.type.startswith("tool.") or event.type == "draft.available" for event in events)
        assert next(event.payload for event in events if event.type == "message.delta")["source_refs"] == []
    assert seen[1][0] > seen[0][0] and all(not tools for _, tools in seen)
    with pytest.raises(IdentityDenied):
        runtime.prepare((credentials[0], credentials[1], credentials[2], uuid4()), AgentRequest(conversation.conversation_id, "cross workspace", Mode.CHAT))
    with owner.transaction(read_only=True) as connection:
        rows = connection.execute(text("SELECT class_id,term_id FROM class_os.business_audit WHERE action='agent.run.completed'")).all()
        assert len(rows) == 2 and all(row == (None, None) for row in rows)
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0


@pytest.mark.db
async def test_workspace_chat_http_requires_identity_csrf_and_refuses_domain_modes(roster):
    business, query, _, _, boundary, _, _ = roster
    runtime = PydanticAgentRuntime(query)
    app = create_app(Settings(), identity=boundary, business=business, query=query, agent=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        context = (await client.get("/api/identity/context")).json()
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": context["csrf_token"]}
        login = (await client.post("/api/identity/login", json={"password": PASSWORD}, headers=headers)).json()
        headers["x-class-os-csrf"] = login["csrf_token"]
        base = "/api/workspaces/" + login["subject"]["workspace_id"] + "/agent"
        body = {"schema_version": "classmatter.workspace-conversation-request.v1"}
        assert (await client.post(base + "/workspace-conversations", json=body)).status_code == 403
        reply = await client.post(base + "/workspace-conversations", json=body, headers=headers)
        assert reply.status_code == 200 and reply.json()["scope"] == "workspace"
        turn = {"conversation_id": reply.json()["conversation_id"], "text": "hello without a class", "mode": "chat"}
        response = await client.post(base + "/events", json=turn, headers=headers)
        assert response.status_code == 200 and "event: run.completed" in response.text
        for mode in ("read", "draft"):
            assert (await client.post(base + "/events", json={**turn, "mode": mode}, headers=headers)).status_code == 409
        assert (await client.post(base + "/workspace-conversations", json={**body, "class_id": str(uuid4())}, headers=headers)).status_code == 400
        assert (await client.post(base + "/conversations", json={}, headers=headers)).status_code == 409


@pytest.mark.db
def test_original_browser_workspace_chat_without_any_class(roster):
    business, query, _, _, boundary, owner, _ = roster
    seen = []
    def respond(messages, info):
        assert not info.function_tools
        seen.append(len(messages))
        return ModelResponse(parts=[TextPart("合成无班级聊天回复")])
    runtime = PydanticAgentRuntime(query, model_factory=lambda _: FunctionModel(respond))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    app = create_app(Settings(port=port), identity=boundary, business=business, query=query, agent=runtime)
    mount_web(app, root / "apps/web/dist")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, proxy_headers=False, access_log=False, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(["node", "tests/workspace-chat-browser.mjs"], cwd=root / "apps/web",
            env=dict(os.environ, CLASS_OS_TEST_URL=f"http://127.0.0.1:{port}"), capture_output=True,
            text=True, encoding="utf-8", timeout=90, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stdout + result.stderr
        assert len(seen) == 2 and seen[1] > seen[0]
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.school_class")).scalar_one() == 0
            assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
    finally:
        server.should_exit = True; thread.join(timeout=8)
        assert not thread.is_alive()


@pytest.mark.db
async def test_d1_adds_only_workspace_chat_without_ephemeral_class_bypass(control):
    from test_durable_conversation_http import setup, client
    value = setup(control)
    base = f"/api/workspaces/{value.auth[3]}/agent"
    scoped = value.sdk.conversation(value.auth)
    async with client(value) as api:
        assert (await api.post(base + "/conversations", json={}, headers=value.headers)).status_code == 404
        assert (await api.post(base + "/record-note/events", json={"schema_version": "class-os.agent-record-note-request.v1", "conversation_id": str(scoped.conversation_id), "text": "synthetic text"}, headers=value.headers)).status_code == 404
        reply = await api.post(base + "/workspace-conversations", json={"schema_version": "classmatter.workspace-conversation-request.v1"}, headers=value.headers)
        assert reply.status_code == 200
        body = {"conversation_id": reply.json()["conversation_id"], "mode": "chat", "text": "synthetic ordinary chat"}
        result = await api.post(base + "/events", json=body, headers=value.headers)
        assert result.status_code == 200 and "event: run.completed" in result.text
        assert (await api.post(base + "/events", json={**body, "mode": "read"}, headers=value.headers)).status_code == 409
        assert (await api.post(base + "/events", json={**body, "conversation_id": str(scoped.conversation_id)}, headers=value.headers)).status_code == 409
