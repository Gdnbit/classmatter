import json
from uuid import uuid4

import httpx
import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from openai import AsyncOpenAI
from sqlalchemy import text

from class_os.application.agent import AgentRequest, DraftKind, Mode, AgentRejected
from class_os.application.model_configuration import ModelConfiguration, Protocol
from class_os.infrastructure.model_provider import model_for_configuration
from class_os.domain.roster import ChangeClass
from class_os.domain.record_note import RecordNoteCandidate
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.agent import RecordNoteCandidateResponse
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity
from test_model_configuration import login
from test_agent_api_protocol import protocol_reply, MODEL, KEY


@pytest.mark.parametrize("mode,kind", [(Mode.READ, DraftKind.RECORD_NOTE), (Mode.CHAT, DraftKind.RECORD_NOTE), (Mode.DRAFT, "record-note")])
def test_note_profile_requires_explicit_typed_draft_before_any_query(mode, kind):
    with pytest.raises(AgentRejected):
        PydanticAgentRuntime(object()).prepare((), AgentRequest(uuid4(), "合成原文", mode, kind))


def test_domain_candidate_matches_closed_wire_without_creating_a_record():
    payload = RecordNoteCandidate.from_message("合成原文", "原文").canonical()
    assert RecordNoteCandidateResponse.model_validate(payload).model_dump(mode="json") == payload


@pytest.mark.db
@pytest.mark.parametrize("fault", [None, "invented", "archived"])
async def test_record_note_profile_is_verbatim_ephemeral_and_cannot_save_or_release_stale_scope(roster, fault):
    business, query, _, auth, _, owner, _ = roster
    classroom, _, _ = seed(roster)
    message, quote = "请摘录：🌱合成原文待核对。", "🌱合成原文待核对。"
    visible = []
    def reply(messages, info):
        visible.extend(tool.name for tool in info.function_tools)
        returned = next((part for part in messages[-1].parts if isinstance(part, ToolReturnPart)), None) if isinstance(messages[-1], ModelRequest) else None
        if returned:
            assert returned.content["status"] == "unverified-user-note"
            if fault == "archived":
                submit(business, auth, ChangeClass("class.archive", classroom.class_id, classroom.term_id,
                    query.context(*auth).version, "合成归档"))
            return ModelResponse(parts=[TextPart("原文草稿，尚未核实或保存。")])
        return ModelResponse(parts=[ToolCallPart("record_note_draft", {"note_quote": "合成编造结论" if fault == "invented" else quote})])
    runtime = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(reply))
    conversation = runtime.conversation(auth)
    turn = AgentRequest(conversation.conversation_id, message, Mode.DRAFT, DraftKind.RECORD_NOTE)
    events = [event async for event in runtime.stream(auth, turn)]
    assert set(visible) == {"record_note_draft"}
    if fault:
        assert events[-1].type == "run.failed" and not conversation.history
        assert not any(event.type in ("draft.available", "message.delta") for event in events)
    else:
        assert events[-1].type == "run.completed"
        candidate = next(event.payload["draft"] for event in events if event.type == "draft.available")
        assert candidate["status"] == "unverified-user-note" and candidate["note_quote"] == quote
        assert not any(field in candidate for field in ("student_id", "occurred_at", "kind", "command"))
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0


@pytest.mark.db
async def test_new_record_note_route_is_explicit_closed_and_old_mode_wire_unchanged(roster):
    business, query, _, auth, boundary, _, _ = roster
    _, student, _ = seed(roster)
    runtime = PydanticAgentRuntime(query)
    app = create_app(Settings(), identity=boundary, business=business, query=query, agent=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        headers, workspace = await login(client)
        base = f"/api/workspaces/{workspace}/agent"
        legacy = (await client.post(base + "/conversations", json={}, headers=headers)).json()
        body = {"schema_version": "class-os.agent-record-note-request.v1", "conversation_id": legacy["conversation_id"], "text": "合成需要人工核对的原文"}
        path = base + "/record-note/events"
        assert (await client.post(path, json=body)).status_code == 403
        assert (await client.post(path, json={**body, "student_id": str(student.student_id)}, headers=headers)).status_code == 400
        response = await client.post(path, json=body, headers=headers)
        assert response.status_code == 200 and "event: draft.available" in response.text and "unverified-user-note" in response.text
        assert "event: run.completed" in response.text
        assert (await client.post(base + "/events", json={"conversation_id": legacy["conversation_id"], "text": "合成", "mode": "record-note"}, headers=headers)).status_code == 400
        scoped = (await client.post(base + "/conversations", json={"schema_version": "class-os.agent-conversation-request.v2", "student_id": str(student.student_id)}, headers=headers)).json()
        assert (await client.post(path, json={**body, "conversation_id": scoped["conversation_id"]}, headers=headers)).status_code == 409


@pytest.mark.db
@pytest.mark.parametrize("protocol", ["chat-completions", "responses"])
@pytest.mark.parametrize("invented", [False, True])
async def test_record_note_uses_both_real_sdk_protocol_adapters_without_business_write(roster, protocol, invented):
    _, query, _, auth, _, owner, _ = roster
    seed(roster)
    calls = []
    def reply(request):
        body = json.loads(request.content)
        names = {tool["name"] if protocol == "responses" else tool["function"]["name"] for tool in body["tools"]}
        assert names == {"record_note_draft"}
        calls.append(body)
        if protocol == "responses":
            assert body["store"] is False and "conversation" not in body and "previous_response_id" not in body
        return httpx.Response(200, json=protocol_reply(protocol, body, len(calls)))
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply), trust_env=False, follow_redirects=False) as http:
        async with AsyncOpenAI(api_key=KEY, base_url="http://127.0.0.1/v1", organization="", project="", max_retries=0, http_client=http) as client:
            model = model_for_configuration(ModelConfiguration(Protocol(protocol), MODEL, "http://127.0.0.1/v1"), client)
            runtime = PydanticAgentRuntime(query, model_factory=lambda request: model, provider_label="synthetic-api-protocol")
            conversation = runtime.conversation(auth)
            source = "不同的合成本轮文本" if invented else "合成API待核对原文"
            events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, source, Mode.DRAFT, DraftKind.RECORD_NOTE))]
    if invented:
        assert events[-1].type == "run.failed" and len(calls) == 1 and not conversation.history
        assert not any(event.type in ("draft.available", "message.delta") for event in events)
    else:
        assert events[-1].type == "run.completed" and len(calls) == 2
        assert next(event.payload["draft"] for event in events if event.type == "draft.available")["note_quote"] == source
        assert "尚未核实" in next(event.payload["text"] for event in events if event.type == "message.delta")
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
