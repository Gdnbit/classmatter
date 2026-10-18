"""Versioned definitions of the two existing tools, not an extension registry."""
import json
from pathlib import Path

import pytest
from pydantic_ai import Tool
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.agent import AgentRequest, Mode, DraftKind
from class_os.application.agent_tool_contracts import catalog, for_mode
from class_os.infrastructure.agent import PydanticAgentRuntime
from test_activity_gateway import seed
from test_roster_gateway import roster
from test_identity import identity


def test_catalog_is_closed_versioned_and_returns_independent_copies():
    first = catalog()
    assert {item["name"] for item in first} == {"attention_list", "task_draft", "record_note_draft"}
    assert all(item["schema_version"] == "class-os.tool-contract.v1" and item["version"] == 1 for item in first)
    assert [item["name"] for item in for_mode(Mode.READ)] == ["attention_list"]
    assert [item["name"] for item in for_mode(Mode.DRAFT)] == ["task_draft"]
    assert for_mode(Mode.CHAT) == ()
    assert [item["name"] for item in for_mode(Mode.DRAFT, DraftKind.RECORD_NOTE)] == ["record_note_draft"]
    first[0]["parameters_json_schema"]["properties"]["sql"] = {"type": "string"}
    assert "sql" not in catalog()[0]["parameters_json_schema"]["properties"]
    with pytest.raises(ValueError):
        for_mode("read")


def test_tool_snapshots_match_application_definitions():
    root = Path(__file__).resolve().parents[2] / "contracts/tools"
    assert {file.name for file in root.glob("*.json")} == {"attention-list.v1.json", "task-draft.v1.json", "record-note-draft.v1.json"}
    for item in catalog():
        assert json.loads((root / (item["name"].replace("_", "-") + ".v1.json")).read_text(encoding="utf-8")) == item


@pytest.mark.db
@pytest.mark.parametrize("mutation", ["parameters", "description", "name", "kind", "strict"])
async def test_native_sdk_definition_drift_prevents_even_provider_context(roster, monkeypatch, mutation):
    _, query, _, auth, _, _, _ = roster
    seed(roster)
    entered = []
    def provider(request):
        entered.append(True)
        return FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("must not be invoked")]))
    original_definition = Tool.tool_def.fget
    def changed_definition(native):
        definition = original_definition(native)
        if mutation == "parameters":
            definition.parameters_json_schema = {"type": "object", "additionalProperties": True}
        elif mutation == "description":
            definition.description = "Synthetic unauthorized capability expansion"
        elif mutation == "name":
            definition.name = "commands_commit"
        elif mutation == "kind":
            definition.kind = "external"
        else:
            definition.strict = True
        return definition
    monkeypatch.setattr(Tool, "tool_def", property(changed_definition))
    runtime = PydanticAgentRuntime(query, model_factory=provider)
    conversation = runtime.conversation(auth)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "合成契约漂移", Mode.READ))]
    assert not entered and events[-1].type == "run.failed" and not conversation.history
    assert not any(event.type in ("tool.started", "message.delta", "draft.available", "run.completed") for event in events)


@pytest.mark.db
async def test_actual_sdk_definitions_match_each_registered_mode_without_business_write(roster):
    _, query, _, auth, _, owner, _ = roster
    seed(roster)
    observed = []
    def provider(request):
        def reply(messages, info):
            expected = for_mode(request.mode)
            assert [(tool.name, tool.description, tool.parameters_json_schema) for tool in info.function_tools] == [
                (item["name"], item["description"], item["parameters_json_schema"]) for item in expected]
            observed.append(request.mode)
            returned = any(isinstance(part, ToolReturnPart) for part in messages[-1].parts) if isinstance(messages[-1], ModelRequest) else False
            if expected and not returned:
                name = expected[0]["name"]
                return ModelResponse(parts=[ToolCallPart(name, {"title": "合成接口草稿"} if name == "task_draft" else {})])
            return ModelResponse(parts=[TextPart("合成契约响应；不代表语义质量验收")])
        return FunctionModel(reply)
    runtime = PydanticAgentRuntime(query, model_factory=provider)
    conversation = runtime.conversation(auth)
    for mode in Mode:
        events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "合成版本接口", mode))]
        assert events[-1].type == "run.completed", runtime.last_failure_type
    assert set(observed) == set(Mode)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
