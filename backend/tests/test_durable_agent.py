"""Original SDK FunctionModel on owned real PostgreSQL, never paid credentials."""
import asyncio
from contextlib import aclosing
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.conversation_worker import ConversationWorkerGateway
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.durable_agent import DurableChatRuntime
from test_conversation_interaction_gateway import prepared
from test_conversation_control import control, storage, roster, identity


def setup(control, respond=None, timeout=10):
    value = prepared(control)
    value.thread = uuid4()
    value.gateway.create_conversation(*value.auth, value.ids["class"], value.ids["term"], value.thread, uuid4(), "合成班务讨论")
    value.worker = ConversationWorkerGateway(value.gateway.identity, value.store, clock=lambda: control[7][0])
    options = {"model_factory": lambda request: FunctionModel(respond)} if respond else {}
    value.sdk = PydanticAgentRuntime(value.query, timeout=timeout, **options)
    value.runtime = DurableChatRuntime(value.worker, value.query, value.sdk)
    return value


def stream(value, key, text="合成讨论输入"):
    return value.runtime.stream(value.auth, value.ids["class"], value.ids["term"], value.thread, key, text)


def status(value, key):
    return value.query.turn_status(*value.auth, value.ids["class"], value.ids["term"], value.thread, key)


@pytest.mark.db
async def test_original_sdk_persist_before_release_replay_and_rebuild_history(control):
    calls = []
    def respond(messages, info):
        calls.append(messages)
        assert not info.function_tools
        return ModelResponse(parts=[TextPart("合成回复")])
    value = setup(control, respond)
    key = uuid4()
    events = []
    async for event in stream(value, key):
        if event.type in ("message.delta", "run.completed"):
            assert status(value, key)["state"] == "completed"
        events.append(event)
    assert events[-1].type == "run.completed" and len(calls) == 1
    assert len({item.run_id for item in events}) == 1
    assert events[0].run_id == status(value, key)["run_id"]
    assert not [event async for event in stream(value, key)]
    assert len(calls) == 1 and not value.sdk.memory._items
    # A new process-local SDK object hydrates only authorized visible text.
    value.sdk = PydanticAgentRuntime(value.query, model_factory=lambda request: FunctionModel(respond))
    value.runtime = DurableChatRuntime(value.worker, value.query, value.sdk)
    again = [event async for event in stream(value, uuid4(), "合成第二轮")]
    assert again[-1].type == "run.completed" and len(calls) == 2
    history_text = str(calls[-1])
    assert "合成讨论输入" in history_text and "合成回复" in history_text
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE role='assistant'")).scalar_one() == 2


@pytest.mark.db
async def test_finish_audit_failure_never_releases_model_answer(control, monkeypatch):
    value = setup(control)
    original = value.worker.finish_run
    def broken(*args, **kwargs):
        if args[2] == "completed":
            raise RuntimeError("synthetic persistence outage")
        return original(*args, **kwargs)
    monkeypatch.setattr(value.worker, "finish_run", broken)
    key = uuid4()
    events = [event async for event in stream(value, key)]
    assert events[-1].type == "run.failed"
    assert not any(item.type in ("message.delta", "run.completed") for item in events)
    assert status(value, key)["state"] == "unknown"
    assert not value.sdk.memory._items


@pytest.mark.db
@pytest.mark.parametrize("abort", [False, True])
async def test_timeout_or_disconnect_stops_sdk_and_never_redispatches(control, abort):
    entered, stopped = asyncio.Event(), asyncio.Event()
    async def respond(messages, info):
        entered.set()
        try:
            await asyncio.sleep(30)
        finally:
            stopped.set()
        return ModelResponse(parts=[TextPart("not reached")])
    value = setup(control, respond, timeout=.15 if not abort else 10)
    key = uuid4()
    if abort:
        async with aclosing(stream(value, key)) as events:
            assert (await anext(events)).type == "run.started"
            await entered.wait()
    else:
        events = [event async for event in stream(value, key)]
        assert events[-1].type == "run.failed"
        assert not any(item.type == "message.delta" for item in events)
    assert stopped.is_set() and value.sdk.active == 0 and not value.sdk.memory._items
    assert status(value, key)["state"] == "unknown"
    assert not [event async for event in stream(value, key)]


@pytest.mark.db
async def test_clear_after_finish_commit_before_release_drops_buffered_answer(control, monkeypatch):
    from class_os.domain.conversation_control import ClearConversation
    value = setup(control)
    original = value.worker.finish_run
    def finish_then_clear(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[2] == "completed":
            history = value.query.conversation_history(*value.auth, value.ids["class"], value.ids["term"], value.thread)
            proposal = value.worker.preview(*value.auth, ClearConversation(value.thread, value.ids["class"], value.ids["term"], history.history.version))
            nonce = value.worker.approve(*value.auth, proposal.proposal_id, proposal.payload_hash)
            value.worker.commit(*value.auth, proposal.proposal_id, uuid4(), nonce)
        return result
    monkeypatch.setattr(value.worker, "finish_run", finish_then_clear)
    events = [event async for event in stream(value, uuid4())]
    assert events[-1].type == "run.failed"
    assert not any(item.type in ("message.delta", "run.completed") for item in events)


@pytest.mark.db
@pytest.mark.parametrize("fault", ["expired", "cancelled"])
async def test_dispatch_rechecks_current_lease_and_cancel_before_sdk(control, monkeypatch, fault):
    calls = []
    def respond(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[TextPart("must not execute")])
    value = setup(control, respond)
    original = value.worker.claim
    def delayed(*args):
        ticket = original(*args)
        if fault == "expired":
            control[7][0] += timedelta(seconds=61)
        else:
            value.worker.cancel_run(value.auth, value.ids["class"], value.ids["term"], value.thread, ticket.run.run_id, ticket.run.version)
        return ticket
    monkeypatch.setattr(value.worker, "claim", delayed)
    key = uuid4()
    events = [event async for event in stream(value, key)]
    assert events[-1].type == "run.failed" and not calls
    assert not any(item.type in ("run.started", "message.delta", "run.completed") for item in events)
    if fault == "expired":
        value.worker.reconcile_run(value.auth, value.ids["class"], value.ids["term"], value.thread, status(value, key)["run_id"])
        assert status(value, key)["state"] == "interrupted"
    else:
        assert status(value, key)["state"] == "unknown"
