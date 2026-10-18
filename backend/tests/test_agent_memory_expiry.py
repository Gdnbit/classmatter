"""Memory TTL is independent of identity validity and checked at release."""
from datetime import timedelta
from contextlib import asynccontextmanager

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.agent import AgentRequest, AgentRejected, DraftKind, Mode
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.agent_memory import ConversationMemory
from test_activity_gateway import seed
from test_roster_gateway import roster
from test_identity import identity


@pytest.mark.db
@pytest.mark.parametrize("mode,kind,student_scope", [(Mode.READ, DraftKind.TASK, False),
    (Mode.DRAFT, DraftKind.TASK, False), (Mode.DRAFT, DraftKind.RECORD_NOTE, False),
    (Mode.CHAT, DraftKind.TASK, False), (Mode.READ, DraftKind.TASK, True)])
async def test_memory_expires_during_model_never_releases_result_or_history(roster, mode, kind, student_scope):
    _, query, _, auth, _, owner, business_clock = roster
    _, student, _ = seed(roster)
    memory_clock = [business_clock[0]]
    memory = ConversationMemory(clock=lambda: memory_clock[0])
    def respond(messages, info):
        returned = isinstance(messages[-1], ModelRequest) and any(isinstance(part, ToolReturnPart) for part in messages[-1].parts)
        if info.function_tools and not returned:
            tool = info.function_tools[0].name
            args = {"title": "合成短期草稿"} if tool == "task_draft" else {"note_quote": "合成原文"} if tool == "record_note_draft" else {}
            return ModelResponse(parts=[ToolCallPart(tool, args)])
        memory_clock[0] += timedelta(minutes=15)
        return ModelResponse(parts=[TextPart("TTL后不应交付")])
    runtime = PydanticAgentRuntime(query, memory=memory, model_factory=lambda request: FunctionModel(respond))
    conversation = runtime.conversation(auth, student_id=student.student_id if student_scope else None)
    request = AgentRequest(conversation.conversation_id, "合成原文", mode, kind)
    events = [event async for event in runtime.stream(auth, request)]
    assert events[-1].type == "run.failed"
    assert not any(event.type in ("message.delta", "draft.available", "run.completed") for event in events)
    assert conversation.history == [] and conversation.turns == 0 and runtime.active == 0 and not conversation.active
    assert conversation.conversation_id not in memory._items
    with pytest.raises(AgentRejected):
        runtime.prepare(auth, request)
    fresh = runtime.conversation(auth)
    assert fresh.conversation_id != conversation.conversation_id and fresh.history == []
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.record_revision")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='agent.run.completed'")).scalar_one() == 0


@pytest.mark.db
@pytest.mark.parametrize("stage", ["started", "completed"])
async def test_memory_expiry_during_audit_wait_does_not_enter_provider_or_release(roster, monkeypatch, stage):
    _, query, _, auth, _, _, clock = roster
    seed(roster)
    memory_clock = [clock[0]]
    memory = ConversationMemory(clock=lambda: memory_clock[0])
    original = query.agent_audit
    def audit(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[2] == stage:
            memory_clock[0] += timedelta(minutes=15)
        return result
    monkeypatch.setattr(query, "agent_audit", audit)
    entered = []
    def factory(request):
        entered.append(True)
        return FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("合成回答")]))
    runtime = PydanticAgentRuntime(query, memory=memory, model_factory=factory)
    conversation = runtime.conversation(auth)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "合成对话", Mode.CHAT))]
    assert events[-1].type == "run.failed"
    assert not any(event.type in ("message.delta", "draft.available", "run.completed") for event in events)
    assert len(entered) == (0 if stage == "started" else 1)
    assert not conversation.history and conversation.turns == 0 and not conversation.active and runtime.active == 0


@pytest.mark.db
@pytest.mark.parametrize("stage", ["tool-entry", "query-return", "model-context"])
async def test_expired_tool_or_model_context_cannot_continue_sdk_or_source_delivery(roster, monkeypatch, stage):
    _, query, _, auth, _, _, clock = roster
    seed(roster)
    memory_clock = [clock[0]]
    memory = ConversationMemory(clock=lambda: memory_clock[0])
    queried, called = [], []
    original = query.work_snapshot
    def snapshot(*args, **kwargs):
        queried.append(True)
        result = original(*args, **kwargs)
        if stage == "query-return":
            memory_clock[0] += timedelta(minutes=15)
        return result
    monkeypatch.setattr(query, "work_snapshot", snapshot)
    def respond(messages, info):
        called.append(True)
        if stage == "tool-entry":
            memory_clock[0] += timedelta(minutes=15)
        return ModelResponse(parts=[ToolCallPart("attention_list", {})])
    @asynccontextmanager
    async def context(credentials, request):
        if stage == "model-context":
            memory_clock[0] += timedelta(minutes=15)
        yield FunctionModel(respond)
    runtime = PydanticAgentRuntime(query, memory=memory, model_context=context)
    conversation = runtime.conversation(auth)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "合成查询", Mode.READ))]
    assert events[-1].type == "run.failed"
    assert not any(event.type in ("tool.completed", "draft.available", "message.delta", "run.completed") for event in events)
    assert len(called) == (0 if stage == "model-context" else 1)
    assert len(queried) == (1 if stage == "query-return" else 0)
    assert not conversation.history and not conversation.active and runtime.active == 0
    assert conversation.conversation_id not in memory._items


@pytest.mark.db
async def test_expired_second_turn_does_not_replace_history_or_extend_original_ttl(roster):
    _, query, _, auth, _, _, clock = roster
    seed(roster)
    memory_clock = [clock[0]]
    memory = ConversationMemory(clock=lambda: memory_clock[0])
    phase = ["valid"]
    def respond(messages, info):
        if phase[0] == "expire":
            memory_clock[0] += timedelta(minutes=1)
        return ModelResponse(parts=[TextPart("合成有效前轮" if phase[0] == "valid" else "不应成为新历史")])
    runtime = PydanticAgentRuntime(query, memory=memory, model_factory=lambda request: FunctionModel(respond))
    conversation = runtime.conversation(auth)
    expires_at = conversation.expires_at
    request = AgentRequest(conversation.conversation_id, "合成对话", Mode.CHAT)
    first = [event async for event in runtime.stream(auth, request)]
    assert first[-1].type == "run.completed" and conversation.history and conversation.turns == 1
    phase[0] = "expire"
    memory_clock[0] += timedelta(minutes=14)
    second = [event async for event in runtime.stream(auth, request)]
    assert second[-1].type == "run.failed"
    assert not any(event.type == "message.delta" for event in second)
    assert conversation.turns == 1 and conversation.expires_at == expires_at
    assert not conversation.history and conversation.conversation_id not in memory._items
