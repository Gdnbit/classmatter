"""Real vendor SDK protocol, offline HTTP responses, actual authorized QG."""
import json

import httpx
import pytest
from openai import AsyncOpenAI
from class_os.application.model_configuration import ModelConfiguration, Protocol
from class_os.infrastructure.model_provider import model_for_configuration
from sqlalchemy import text

from class_os.application.agent import AgentRequest, Mode
from class_os.infrastructure.agent import PydanticAgentRuntime
from test_activity_gateway import seed
from test_roster_gateway import roster
from test_identity import identity


MODEL = "class-os-synthetic-api-fixture"
KEY = "synthetic-offline-api-fixture-only"


def protocol_reply(protocol, body, index, *, malicious=False):
    if protocol == "chat-completions":
        tools = body.get("tools", [])
        returned = body["messages"][-1]["role"] == "tool"
        if tools and not returned:
            tool = "commands_commit" if malicious else tools[0]["function"]["name"]
            arguments = {"title": "合成API未提交草稿"} if tool == "task_draft" else {}
            if tool == "record_note_draft":
                arguments = {"note_quote": "合成API待核对原文"}
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call_fixture_{index}", "type": "function", "function": {"name": tool, "arguments": json.dumps(arguments)}}]}
            finish = "tool_calls"
        else:
            message, finish = {"role": "assistant", "content": "合成 API 协议响应，不是真实模型质量证据。"}, "stop"
        return {"id": f"chatcmpl_fixture_{index}", "object": "chat.completion", "created": 1, "model": MODEL,
                "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    tools = body.get("tools", [])
    returned = body["input"][-1].get("type") == "function_call_output"
    if tools and not returned:
        tool = "commands_commit" if malicious else tools[0]["name"]
        arguments = {"title": "合成API未提交草稿"} if tool == "task_draft" else {}
        if tool == "record_note_draft":
            arguments = {"note_quote": "合成API待核对原文"}
        output = [{"id": f"fc_fixture_{index}", "type": "function_call", "call_id": f"call_fixture_{index}",
                   "name": tool, "arguments": json.dumps(arguments), "status": "completed"}]
    else:
        output = [{"id": f"msg_fixture_{index}", "type": "message", "role": "assistant", "status": "completed",
                   "content": [{"type": "output_text", "text": "合成 API 协议响应，不是真实模型质量证据。", "annotations": []}]}]
    return {"id": f"resp_fixture_{index}", "object": "response", "created_at": 1, "status": "completed", "model": MODEL,
            "output": output, "parallel_tool_calls": False, "tools": [],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                      "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}}


@pytest.mark.db
@pytest.mark.parametrize("protocol", ("chat-completions", "responses"))
@pytest.mark.parametrize("fault", (None, "unknown-tool", "http-error", "ungrounded-answer", "truncated", "truncated-draft"))
async def test_sdk_api_protocol_uses_existing_read_draft_boundary_without_business_writes(roster, protocol, fault, monkeypatch):
    _, query, _, credentials, _, owner, _ = roster
    seed(roster)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-environment-key-must-not-be-read")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://must-not-contact.invalid/v1")
    monkeypatch.setenv("OPENAI_ORG_ID", "synthetic-org-must-not-inherit")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "synthetic-project-must-not-inherit")
    requests = []
    def reply(request):
        assert str(request.url) == "http://127.0.0.1/v1/" + ("responses" if protocol == "responses" else "chat/completions")
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.headers.get("openai-organization", "") == ""
        assert request.headers.get("openai-project", "") == ""
        body = json.loads(request.content)
        assert body["model"] == MODEL
        assert body["max_output_tokens" if protocol == "responses" else "max_completion_tokens"] == 1024
        assert all(value not in request.content.decode() for value in credentials[:3])
        requests.append(body)
        if fault == "http-error":
            return httpx.Response(503, json={"error": {"message": "synthetic-sensitive-error-canary", "type": "server_error"}})
        if fault == "ungrounded-answer":
            body = {**body, "tools": []}
        packet = protocol_reply(protocol, body, len(requests), malicious=fault == "unknown-tool")
        if fault in ("truncated", "truncated-draft") and len(requests) == 2:
            if protocol == "chat-completions":
                packet["choices"][0]["finish_reason"] = "length"
            else:
                packet.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        return httpx.Response(200, json=packet)
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply), trust_env=False, follow_redirects=False, timeout=2) as http_client:
        async with AsyncOpenAI(api_key=KEY, base_url="http://127.0.0.1/v1", organization="", project="",
                               http_client=http_client, max_retries=0) as client:
            model = model_for_configuration(ModelConfiguration(Protocol(protocol), MODEL, "http://127.0.0.1/v1"), client)
            runtime = PydanticAgentRuntime(query, model_factory=lambda request: model, provider_label="synthetic-api-protocol")
            conversation = runtime.conversation(credentials)
            for mode in ((Mode.DRAFT,) if fault == "truncated-draft" else (Mode.READ,) if fault else (Mode.READ, Mode.READ, Mode.DRAFT)):
                events = [event async for event in runtime.stream(credentials, AgentRequest(conversation.conversation_id, "合成协议验证", mode))]
                assert events[0].payload["provider"] == "synthetic-api-protocol"
                if fault:
                    assert events[-1].type == "run.failed"
                    assert not any(event.type in ("message.delta", "draft.available") for event in events)
                    assert conversation.history == [] and conversation.turns == 0
                    assert "synthetic-sensitive-error-canary" not in str(events)
                    assert len(requests) == (2 if fault in ("truncated", "truncated-draft") else 1)
                else:
                    assert events[-1].type == "run.completed", runtime.last_failure_type
                    if mode == Mode.READ:
                        answer = next(event for event in events if event.type == "message.delta")
                        assert len(answer.payload["source_refs"]) == 1
                    else:
                        assert next(event for event in events if event.type == "draft.available").payload["draft"]["title"] == "合成API未提交草稿"
                assert runtime.active == 0 and not conversation.active
    if not fault:
        assert conversation.turns == 3 and len(requests) == 6
    for body in requests:
        tools = body.get("tools", [])
        names = {tool["name"] if protocol == "responses" else tool["function"]["name"] for tool in tools}
        assert names in ({"attention_list"}, {"task_draft"})
        if protocol == "responses":
            assert body["store"] is False
            assert "previous_response_id" not in body and "conversation" not in body
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
        if not fault:
            assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='activity.today'")).scalar_one() == 2
        else:
            assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='activity.today'")).scalar_one() == (1 if fault == "truncated" else 0)


@pytest.mark.parametrize("label", ("real-provider-unverified", {"secret": "synthetic-canary"}))
def test_provider_label_is_closed_static_metadata_not_model_or_credential_input(label):
    with pytest.raises(ValueError, match="Unsupported synthetic provider label"):
        PydanticAgentRuntime(object(), provider_label=label)
