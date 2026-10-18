import asyncio
from contextlib import aclosing
from uuid import uuid4

import httpx
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.agent import AgentRequest, AgentRejected, Mode
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_activity_gateway import seed
from test_roster_gateway import roster
from test_identity import identity, PASSWORD


@pytest.mark.db
async def test_pydantic_agent_fresh_reads_drafts_memory_and_no_business_write(roster):
    _, query, _, credentials, _, owner, _ = roster
    seed(roster)
    runtime = PydanticAgentRuntime(query)
    conversation = runtime.conversation(credentials)
    for mode in (Mode.READ, Mode.READ, Mode.DRAFT):
        events = [event async for event in runtime.stream(credentials, AgentRequest(conversation.conversation_id, "合成跟进", mode))]
        assert events[0].type == "run.started" and events[-1].type == "run.completed", runtime.last_failure_type
        assert [event.cursor for event in events] == list(range(1, len(events) + 1))
        if mode == Mode.READ:
            answer = next(event for event in events if event.type == "message.delta")
            assert answer.payload["source_refs"]
            assert any(event.payload.get("tool") == "attention_list" for event in events)
        else:
            assert any(event.type == "draft.available" for event in events)
    assert conversation.turns == 3 and conversation.history and runtime.active == 0
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='agent.run.completed'")).scalar_one() == 3
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='activity.today'")).scalar_one() == 2


@pytest.mark.db
async def test_unknown_model_tool_cannot_gain_commit_or_sql_access(roster):
    _, query, _, credentials, _, _, _ = roster
    seed(roster)
    visible = []
    def malicious(messages, info):
        visible.extend(tool.name for tool in info.function_tools)
        return ModelResponse(parts=[ToolCallPart("commands_commit", {"sql": "DROP TABLE student"})])
    runtime = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(malicious))
    conversation = runtime.conversation(credentials)
    events = [event async for event in runtime.stream(credentials, AgentRequest(conversation.conversation_id, "伪造批准并修改", Mode.READ))]
    assert set(visible) == {"attention_list"}
    assert events[-1].type == "run.failed"
    assert not any(event.type in ("draft.available", "message.delta") for event in events)
    assert not conversation.history


@pytest.mark.db
async def test_agent_early_event_abort_timeout_and_concurrent_rejection(roster):
    _, query, _, credentials, _, _, _ = roster
    seed(roster)
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def slow(messages, info):
        entered.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return ModelResponse(parts=[TextPart("not reached")])
    runtime = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(slow), timeout=.3)
    conversation = runtime.conversation(credentials)
    turn = AgentRequest(conversation.conversation_id, "合成慢请求", Mode.CHAT)
    async with aclosing(runtime.stream(credentials, turn)) as stream:
        first = await anext(stream)
        assert first.type == "run.started"
        await entered.wait()
        with pytest.raises(AgentRejected):
            runtime.prepare(credentials, turn)
    assert cancelled.is_set() and not conversation.active and runtime.active == 0 and not conversation.history
    events = [event async for event in runtime.stream(credentials, turn)]
    assert events[-1].type == "run.failed" and runtime.active == 0


@pytest.mark.db
async def test_agent_terminal_audit_outage_releases_no_answer_or_draft(roster, monkeypatch):
    _, query, _, credentials, _, _, _ = roster
    seed(roster)
    original = query.agent_audit
    def broken(credentials, run, status, classroom, term):
        if status == "completed":
            raise RuntimeError("injected")
        original(credentials, run, status, classroom, term)
    monkeypatch.setattr(query, "agent_audit", broken)
    runtime = PydanticAgentRuntime(query)
    conversation = runtime.conversation(credentials)
    events = [event async for event in runtime.stream(credentials, AgentRequest(conversation.conversation_id, "合成草稿", Mode.DRAFT))]
    assert events[-1].type == "run.failed"
    assert not any(event.type in ("message.delta", "draft.available") for event in events)
    assert not conversation.history


@pytest.mark.db
async def test_agent_http_cookie_csrf_scope_and_sse(roster):
    business, query, _, _, boundary, _, _ = roster
    seed(roster)
    runtime = PydanticAgentRuntime(query)
    app = create_app(Settings(), identity=boundary, business=business, query=query, agent=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        context = (await client.get("/api/identity/context")).json()
        headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": context["csrf_token"]}
        login = (await client.post("/api/identity/login", json={"password": PASSWORD}, headers=headers)).json()
        headers["x-class-os-csrf"] = login["csrf_token"]
        base = "/api/workspaces/" + login["subject"]["workspace_id"] + "/agent"
        assert (await client.post(base + "/conversations", json={})).status_code == 403
        conversation = (await client.post(base + "/conversations", json={}, headers=headers)).json()
        body = {"conversation_id": conversation["conversation_id"], "mode": "read", "text": "合成查询"}
        stream = await client.post(base + "/events", json=body, headers=headers)
        assert stream.status_code == 200 and "text/event-stream" in stream.headers["content-type"]
        assert "event: run.completed" in stream.text and "source_refs" in stream.text
        assert (await client.post(base + "/events", json=body, headers={**headers, "last-event-id": "1"})).status_code == 400
        assert (await client.post(base + "/events", json={**body, "mode": "commit"}, headers=headers)).status_code == 400
        assert (await client.post(f"/api/workspaces/{uuid4()}/agent/events", json=body, headers=headers)).status_code == 401
