from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import replace

import pytest
from pydantic_ai import ModelResponse, TextPart, ToolCallPart, models
from pydantic_ai.models.function import FunctionModel

from adapter import DeterministicFakeRuntime, EventBuffer, PydanticAIRuntime, RuntimeAuditSink
from boundary import BoundaryViolation, EphemeralDraftBuilder, SyntheticQueryGateway, ToolGateway
from class_os_contracts import RouteMode, RuntimeRequest


models.ALLOW_MODEL_REQUESTS = False


def setup():
    query = SyntheticQueryGateway({"synthetic": {
        "as_of": "2026-10-07T09:00:00+08:00",
        "items": [{"id": "synthetic-1", "bucket": "NEEDS_ME", "title": "synthetic",
                   "source_ref": "synthetic-record@v1"}],
    }})
    drafts = EphemeralDraftBuilder()
    audit = RuntimeAuditSink()
    gateway = ToolGateway(query, drafts)
    request = RuntimeRequest("req", "conv", "run", "synthetic", "synthetic",
                             RouteMode.ANSWER_ONLY, timeout_seconds=1)
    return query, drafts, audit, gateway, request


@pytest.mark.asyncio
async def test_first_event_arrives_while_upstream_is_blocked_and_close_cancels():
    _, drafts, audit, gateway, request = setup()
    entered, release, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def blocked_model(messages, info):
        entered.set()
        try:
            await release.wait()
            return ModelResponse(parts=[TextPart("complete")])
        finally:
            cleaned.set()

    runtime = PydanticAIRuntime(FunctionModel(blocked_model), gateway, audit)
    async with aclosing(runtime.stream(request)) as events:
        first = await asyncio.wait_for(anext(events), 1)
        assert first.type == "run.started"
        await asyncio.wait_for(entered.wait(), 1)
        assert not release.is_set() and not audit.records
    assert cleaned.is_set()
    assert audit.records[-1].outcome == "cancelled"
    assert drafts.committed_business_writes == 0


@pytest.mark.asyncio
async def test_tool_started_arrives_before_query_finishes():
    query, _, audit, gateway, request = setup()
    entered, release = asyncio.Event(), asyncio.Event()
    original = query.attention_list

    async def blocked_query(workspace_id):
        entered.set()
        await release.wait()
        return await original(workspace_id)

    # slots-based synthetic adapter: inject a separate port, not an instance mutation.
    class Query:
        attention_list = staticmethod(blocked_query)

    gateway.query_gateway = Query()
    runtime = DeterministicFakeRuntime(gateway, audit)
    request = replace(request, route_mode=RouteMode.READ,
                      requested_tools=frozenset({"attention.list"}))
    async with aclosing(runtime.stream(request)) as events:
        observed = [await asyncio.wait_for(anext(events), 1) for _ in range(3)]
        await asyncio.wait_for(entered.wait(), 1)
        assert [e.type for e in observed] == ["run.started", "tool.proposed", "tool.started"]
        assert not query.calls and not audit.records
        release.set()
        observed.extend([event async for event in events])
    assert observed[-1].type == "run.completed"
    assert [e.cursor for e in observed] == list(range(1, len(observed) + 1))
    assert audit.records[-1].source_refs == ("synthetic-record@v1",)
    assert next(e for e in observed if e.type == "message.delta").payload["source_refs"] == [
        "synthetic-record@v1",
    ]


@pytest.mark.asyncio
async def test_live_timeout_is_failed_not_completed():
    _, _, audit, gateway, request = setup()

    async def blocked_model(messages, info):
        await asyncio.Event().wait()

    runtime = PydanticAIRuntime(FunctionModel(blocked_model), gateway, audit)
    events = [e async for e in runtime.stream(replace(request, timeout_seconds=0.02))]
    assert events[-1].type == "run.failed"
    assert events[-1].payload == {"code": "timeout"}
    assert sum(e.type in {"run.failed", "run.completed", "run.cancelled"} for e in events) == 1
    assert audit.records[-1].outcome == "timeout"


@pytest.mark.asyncio
async def test_stream_does_not_release_ungrounded_read_answer():
    _, _, audit, gateway, request = setup()
    runtime = PydanticAIRuntime(FunctionModel(
        lambda messages, info: ModelResponse(parts=[TextPart("fabricated current fact")])
    ), gateway, audit)
    events = [e async for e in runtime.stream(replace(request, route_mode=RouteMode.READ))]
    assert events[-1].type == "run.failed"
    assert all(e.type != "message.delta" for e in events)


@pytest.mark.asyncio
async def test_stream_draft_is_ephemeral_and_matches_run_contract():
    _, drafts, audit, gateway, request = setup()
    request = replace(request, route_mode=RouteMode.DRAFT_WRITE,
                      requested_tools=frozenset({"task.draft"}))
    runtime = DeterministicFakeRuntime(gateway, audit)
    result = await runtime.run(request)
    events = [e async for e in runtime.stream(request)]
    assert events == list(result.events)
    assert drafts.committed_business_writes == 0
    assert next(e for e in events if e.type == "draft.available").payload["draft"]["committed"] is False


@pytest.mark.asyncio
async def test_one_active_run_per_instance_and_reusable_after_close():
    _, _, audit, gateway, request = setup()
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_model(messages, info):
        entered.set()
        await release.wait()
        return ModelResponse(parts=[TextPart("ok")])

    runtime = PydanticAIRuntime(FunctionModel(blocked_model), gateway, audit)
    async with aclosing(runtime.stream(request)) as events:
        await asyncio.wait_for(anext(events), 1)
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(BoundaryViolation, match="active run"):
            await runtime.run(replace(request, run_id="second"))
    release.set()
    assert (await runtime.run(replace(request, run_id="next"))).status == "completed"
    assert [r.correlation_id for r in audit.records] == ["run", "next"]


def test_buffer_event_count_is_bounded_with_reserved_failure_terminal():
    buffer = EventBuffer("synthetic")
    for _ in range(127):
        buffer.emit("tool.started", tool="synthetic")
    with pytest.raises(BoundaryViolation, match="event limit"):
        buffer.emit("tool.started", tool="synthetic")
    buffer.emit("run.failed", code="event_limit")
    assert len(buffer.snapshot()) == 128


def test_buffer_payload_size_is_bounded_and_snapshot_is_isolated():
    buffer = EventBuffer("synthetic")
    with pytest.raises(BoundaryViolation, match="event limit"):
        buffer.emit("message.delta", text="x" * 40_000)
    buffer.emit("draft.available", draft={"status": "draft"})
    snapshot = buffer.snapshot()
    snapshot[0].payload["draft"]["status"] = "forged"
    assert buffer.snapshot()[0].payload["draft"]["status"] == "draft"


def test_total_bytes_and_terminal_are_bounded():
    buffer = EventBuffer("synthetic")
    with pytest.raises(BoundaryViolation, match="event limit"):
        for _ in range(20):
            buffer.emit("message.delta", text="x" * 30_000)
    buffer.emit("run.failed", code="event_limit")
    assert buffer._bytes <= buffer.MAX_TOTAL_BYTES
    with pytest.raises(BoundaryViolation, match="terminated"):
        buffer.emit("run.completed")


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -1, 0, 61, True])
@pytest.mark.asyncio
async def test_invalid_deadline_does_not_start_run(timeout):
    _, _, audit, gateway, request = setup()
    runtime = DeterministicFakeRuntime(gateway, audit)
    with pytest.raises(BoundaryViolation, match="timeout"):
        _ = [e async for e in runtime.stream(replace(request, timeout_seconds=timeout))]
    assert not gateway.calls and not audit.records


@pytest.mark.asyncio
async def test_waiting_consumer_cancellation_stops_producer():
    _, _, audit, gateway, request = setup()
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def blocked_model(messages, info):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    runtime = PydanticAIRuntime(FunctionModel(blocked_model), gateway, audit)
    async with aclosing(runtime.stream(request)) as events:
        await anext(events)
        await asyncio.wait_for(entered.wait(), 1)
        waiting = asyncio.create_task(anext(events))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
    assert cleaned.is_set() and audit.records[-1].outcome == "cancelled"


@pytest.mark.asyncio
async def test_fake_query_deadline_cleans_up_and_emits_timeout():
    _, _, audit, gateway, request = setup()
    cleaned = asyncio.Event()

    class Query:
        async def attention_list(self, workspace_id):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    gateway.query_gateway = Query()
    runtime = DeterministicFakeRuntime(gateway, audit)
    events = [e async for e in runtime.stream(replace(
        request, route_mode=RouteMode.READ, requested_tools=frozenset({"attention.list"}),
        timeout_seconds=0.02,
    ))]
    assert events[-1].type == "run.failed" and events[-1].payload == {"code": "timeout"}
    assert cleaned.is_set() and audit.records[-1].outcome == "timeout"


@pytest.mark.asyncio
async def test_oversized_result_fails_closed_without_success_terminal():
    _, _, audit, gateway, request = setup()
    runtime = PydanticAIRuntime(FunctionModel(lambda messages, info: ModelResponse(
        parts=[TextPart("x" * 40_000)])), gateway, audit)
    events = [e async for e in runtime.stream(request)]
    assert events[-1].type == "run.failed"
    assert all(e.type not in {"message.delta", "run.completed"} for e in events)


@pytest.mark.asyncio
async def test_closing_never_started_stream_does_not_start_agent():
    _, _, audit, gateway, request = setup()
    runtime = DeterministicFakeRuntime(gateway, audit)
    stream = runtime.stream(request)
    await stream.aclose()
    assert not gateway.calls and not audit.records


@pytest.mark.asyncio
async def test_combined_read_and_draft_keep_distinct_tool_descriptors():
    _, drafts, audit, gateway, request = setup()

    def invoke(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("attention_list", {}),
                                        ToolCallPart("task_draft", {"title": "synthetic draft"})])
        return ModelResponse(parts=[TextPart("synthetic answer")])

    runtime = PydanticAIRuntime(FunctionModel(invoke), gateway, audit)
    events = [e async for e in runtime.stream(replace(
        request, route_mode=RouteMode.DRAFT_WRITE,
        requested_tools=frozenset({"attention.list", "task.draft"}),
    ))]
    assert events[-1].type == "run.completed"
    assert sorted(gateway.calls) == ["attention.list", "task.draft"]
    assert audit.records[-1].source_refs == ("synthetic-record@v1",)
    assert drafts.committed_business_writes == 0


@pytest.mark.asyncio
async def test_separate_instances_with_shared_gateway_do_not_mix_audit_tools():
    query, _, audit, gateway, request = setup()
    entered, release = asyncio.Event(), asyncio.Event()
    original = query.attention_list

    class Query:
        async def attention_list(self, workspace_id):
            entered.set()
            await release.wait()
            return await original(workspace_id)

    gateway.query_gateway = Query()
    first, second = DeterministicFakeRuntime(gateway, audit), DeterministicFakeRuntime(gateway, audit)
    read = asyncio.create_task(first.run(replace(
        request, route_mode=RouteMode.READ, requested_tools=frozenset({"attention.list"}),
    )))
    await asyncio.wait_for(entered.wait(), 1)
    await second.run(replace(request, run_id="draft", route_mode=RouteMode.DRAFT_WRITE,
                             requested_tools=frozenset({"task.draft"})))
    release.set()
    await read
    assert {record.correlation_id: record.tool_names for record in audit.records} == {
        "run": ("attention.list",), "draft": ("task.draft",),
    }
