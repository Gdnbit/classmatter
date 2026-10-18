from dataclasses import replace
from uuid import uuid4
import json

import httpx
import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, TextPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.agent import AgentRequest, AgentRejected, Mode
from class_os.application.roster import CommandRejected
from class_os.domain.activity import CreateTask
from class_os.domain.roster import CreateStudent, DeactivateStudent, UpdateIdentifier, ChangeClass
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity
from test_model_configuration import login


@pytest.fixture
def scoped(roster):
    business, query, _, auth, _, _, clock = roster
    classroom, student, record = seed(roster)
    submit(business, auth, record)
    submit(business, auth, CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id,
                                     "合成选定任务", student_id=student.student_id))
    other = CreateStudent(uuid4(), classroom.class_id, classroom.term_id, query.context(*auth).version, "合成另一学生")
    submit(business, auth, other)
    submit(business, auth, CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id,
                                     "合成他人任务", student_id=other.student_id))
    submit(business, auth, UpdateIdentifier("student.update_identifier", uuid4(), student.student_id,
        classroom.class_id, classroom.term_id, 1, "合成学校", "school_number", "SYN-01", clock[0]))
    return roster, classroom, student, other


@pytest.mark.db
async def test_selected_student_counts_have_bound_source_and_no_identity_or_narrative_in_provider(scoped):
    roster, classroom, student, _ = scoped
    _, query, _, auth, _, owner, _ = roster
    current = query.work_snapshot(*auth, classroom.class_id, classroom.term_id, student_id=student.student_id)
    total = query.work_snapshot(*auth, classroom.class_id, classroom.term_id)
    assert current.open_tasks == 1 and total.open_tasks == 2 and current.record_count == 1
    assert current.student_id == student.student_id and current.student_version == 2 and current.class_version == 1
    with owner.transaction(read_only=True) as connection:
        row = connection.execute(text("SELECT resource_id,resource_version,payload_hash FROM class_os.business_audit WHERE event_id=:id"), {"id": current.audit_id}).one()
        assert tuple(row) == (student.student_id, 2, current.source_hash)
    captured = []
    def reply(messages, info):
        assert [tool.name for tool in info.function_tools] == ["attention_list"]
        if isinstance(messages[-1], ModelRequest):
            returned = next((part for part in messages[-1].parts if isinstance(part, ToolReturnPart)), None)
            if returned:
                captured.append(returned.content)
                return ModelResponse(parts=[TextPart("合成选定范围的已审计摘要。")])
        return ModelResponse(parts=[ToolCallPart("attention_list", {})])
    runtime = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(reply))
    conversation = runtime.conversation(auth, student_id=student.student_id)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "合成查看选定范围", Mode.READ))]
    assert events[-1].type == "run.completed" and captured[0]["open_tasks"] == 1
    payload = json.dumps(captured, ensure_ascii=False)
    assert all(value not in payload for value in (student.name, str(student.student_id), "合成学生到校记录", "合成他人任务"))
    assert not any(event.type == "draft.available" for event in events)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 2


@pytest.mark.db
async def test_student_scope_cannot_turn_into_class_draft_or_other_student(scoped, monkeypatch):
    roster, _, student, other = scoped
    _, query, _, auth, _, _, _ = roster
    runtime = PydanticAgentRuntime(query)
    conversation = runtime.conversation(auth, student_id=student.student_id)
    with pytest.raises(AgentRejected):
        runtime.prepare(auth, AgentRequest(conversation.conversation_id, "draft", Mode.DRAFT))
    conversation.student_id = other.student_id
    with pytest.raises(AgentRejected):
        runtime.prepare(auth, AgentRequest(conversation.conversation_id, "query", Mode.READ))
    conversation.student_id = student.student_id
    original = query.work_snapshot
    monkeypatch.setattr(query, "work_snapshot", lambda *args, **kwargs: replace(original(*args, **kwargs), student_id=None, student_version=None))
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "query", Mode.READ))]
    assert events[-1].type == "run.failed" and not conversation.history
    assert not any(event.type == "message.delta" for event in events)


@pytest.mark.db
async def test_scoped_v2_conversation_is_explicit_legacy_v1_unchanged_and_inactive_rejected(scoped):
    roster, classroom, student, _ = scoped
    business, query, _, auth, boundary, _, _ = roster
    runtime = PydanticAgentRuntime(query)
    app = create_app(Settings(), identity=boundary, business=business, query=query, agent=runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        headers, workspace = await login(client)
        path = f"/api/workspaces/{workspace}/agent/conversations"
        legacy = (await client.post(path, json={}, headers=headers)).json()
        assert set(legacy) == {"schema_version", "conversation_id", "expires_at", "memory"}
        assert legacy["schema_version"] == "class-os.agent.v1"
        body = {"schema_version": "class-os.agent-conversation-request.v2", "student_id": str(student.student_id)}
        assert (await client.post(path, json={"student_id": str(student.student_id)}, headers=headers)).status_code == 400
        reply = (await client.post(path, json=body, headers=headers)).json()
        assert reply["schema_version"] == "class-os.agent-conversation.v2"
        assert (reply["class_id"], reply["term_id"], reply["student_id"]) == (str(classroom.class_id), str(classroom.term_id), str(student.student_id))
        assert (await client.post(path, json={**body, "student_id": str(uuid4())}, headers=headers)).status_code == 409
    submit(business, auth, DeactivateStudent("student.deactivate", student.student_id, classroom.class_id, classroom.term_id, 2))
    with pytest.raises(CommandRejected):
        query.work_snapshot(*auth, classroom.class_id, classroom.term_id, student_id=student.student_id)


@pytest.mark.db
@pytest.mark.parametrize("fault", ("inactive-before-release", "read-audit"))
async def test_scope_revocation_or_read_audit_failure_never_releases_answer_or_history(scoped, monkeypatch, fault):
    roster, classroom, student, _ = scoped
    business, query, _, auth, _, _, _ = roster
    delivered = []
    def reply(messages, info):
        current = next((part for part in messages[-1].parts if isinstance(part, ToolReturnPart)), None) if isinstance(messages[-1], ModelRequest) else None
        if current:
            delivered.append(current.content)
            if fault == "inactive-before-release":
                submit(business, auth, DeactivateStudent("student.deactivate", student.student_id, classroom.class_id, classroom.term_id, 2))
            return ModelResponse(parts=[TextPart("must not release after scope invalidation")])
        return ModelResponse(parts=[ToolCallPart("attention_list", {})])
    if fault == "read-audit":
        original = query.store.audit
        def failed(connection, binding, action, outcome, now, metadata):
            if action == "activity.today" and metadata["resource_id"] == student.student_id:
                raise RuntimeError("Synthetic scoped audit outage")
            return original(connection, binding, action, outcome, now, metadata)
        monkeypatch.setattr(query.store, "audit", failed)
    runtime = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(reply))
    conversation = runtime.conversation(auth, student_id=student.student_id)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "query", Mode.READ))]
    assert events[-1].type == "run.failed" and conversation.history == [] and runtime.active == 0
    assert not any(event.type in ("message.delta", "draft.available") for event in events)
    assert len(delivered) == (1 if fault == "inactive-before-release" else 0)


@pytest.mark.db
def test_exhausted_owned_scope_can_be_forgotten_without_relaxing_turn_budget(scoped):
    roster, _, student, _ = scoped
    _, query, _, auth, _, _, _ = roster
    runtime = PydanticAgentRuntime(query)
    conversation = runtime.conversation(auth, student_id=student.student_id)
    conversation.turns = 10
    with pytest.raises(AgentRejected):
        runtime.prepare(auth, AgentRequest(conversation.conversation_id, "query", Mode.READ))
    runtime.forget(auth, conversation.conversation_id)
    assert conversation.conversation_id not in runtime.memory._items


@pytest.mark.db
@pytest.mark.parametrize("mode,selected", [(Mode.READ, False), (Mode.DRAFT, False), (Mode.CHAT, False), (Mode.READ, True)])
async def test_late_class_archive_prevents_terminal_answer_draft_and_new_history(scoped, mode, selected):
    roster, classroom, student, _ = scoped
    business, query, _, auth, _, owner, _ = roster
    archived = []
    def reply(messages, info):
        returned = any(isinstance(part, ToolReturnPart) for part in messages[-1].parts) if isinstance(messages[-1], ModelRequest) else False
        if not returned and info.function_tools:
            name = info.function_tools[0].name
            return ModelResponse(parts=[ToolCallPart(name, {"title": "合成归档前草稿"} if name == "task_draft" else {})])
        version = query.context(*auth).version
        submit(business, auth, ChangeClass("class.archive", classroom.class_id, classroom.term_id, version, "合成归档班级"))
        archived.append(True)
        return ModelResponse(parts=[TextPart("归档后不得交付的旧结果")])
    runtime = PydanticAgentRuntime(query, model_factory=lambda request: FunctionModel(reply))
    conversation = runtime.conversation(auth, student_id=student.student_id if selected else None)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "合成查询", mode))]
    assert archived and events[-1].type == "run.failed"
    assert not any(event.type in ("message.delta", "draft.available", "run.completed") for event in events)
    assert conversation.history == [] and conversation.turns == 0 and runtime.active == 0
    with owner.transaction(read_only=True) as connection:
        outcomes = connection.execute(text("SELECT action,outcome FROM class_os.business_audit WHERE action IN ('agent.run.completed','agent.run.failed')")).all()
        assert dict(outcomes) == {"agent.run.completed": "denied", "agent.run.failed": "allowed"}


@pytest.mark.db
@pytest.mark.parametrize("field", ["class_id", "term_id"])
async def test_wrong_projection_parent_scope_never_reaches_model_or_history(scoped, monkeypatch, field):
    roster, _, student, _ = scoped
    _, query, _, auth, _, _, _ = roster
    original = query.work_snapshot
    monkeypatch.setattr(query, "work_snapshot", lambda *args, **kwargs: replace(original(*args, **kwargs), **{field: uuid4()}))
    runtime = PydanticAgentRuntime(query)
    conversation = runtime.conversation(auth, student_id=student.student_id)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "合成错范围", Mode.READ))]
    assert events[-1].type == "run.failed" and not conversation.history
    assert not any(event.type in ("message.delta", "tool.completed") for event in events)
