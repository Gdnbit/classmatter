from __future__ import annotations

import asyncio
import json

import pytest
from pydantic_ai import ModelResponse, TextPart, models
from pydantic_ai.models.function import FunctionModel

from adapter import DeterministicFakeRuntime, PydanticAIRuntime, RuntimeAuditSink
from boundary import EphemeralDraftBuilder, SyntheticQueryGateway, ToolGateway
from transport import create_app

models.ALLOW_MODEL_REQUESTS = False
TOKEN = "synthetic-test-capability-not-production"
ORIGIN = "http://127.0.0.1:8766"


def fixture(model=None):
    query = SyntheticQueryGateway({"synthetic": {"as_of": "synthetic-time", "items": [
        {"id": "synthetic-1", "bucket": "NEEDS_ME", "title": "synthetic",
         "source_ref": "synthetic-record@v1"},
    ]}})
    drafts, audit = EphemeralDraftBuilder(), RuntimeAuditSink()
    gateway = ToolGateway(query, drafts)
    requests = []

    def factory(request):
        requests.append(request)
        if model:
            return PydanticAIRuntime(FunctionModel(model), gateway, audit)
        return DeterministicFakeRuntime(gateway, audit)

    return create_app(factory, token=TOKEN, origin=ORIGIN, workspace_id="synthetic"), requests, drafts, audit


class Exchange:
    def __init__(self, app, *, body=None, headers=None, version="2.3", method="POST",
                 client="127.0.0.1", query=b"", fail_send=False):
        self.app, self.messages = app, []
        self.incoming = asyncio.Queue()
        payload = body if isinstance(body, bytes) else json.dumps(body or {
            "user_text": "synthetic", "route_mode": "read",
        }).encode()
        self.incoming.put_nowait({"type": "http.request", "body": payload, "more_body": False})
        self.first = asyncio.Event()
        self.fail_send = fail_send
        self.scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": version},
                      "http_version": "1.1", "method": method, "path": "/spike/events",
                      "raw_path": b"/spike/events", "query_string": query, "scheme": "http",
                      "server": ("127.0.0.1", 8766), "client": (client, 4567),
                      "headers": headers if headers is not None else [
                          (b"host", b"127.0.0.1:8766"), (b"origin", ORIGIN.encode()),
                          (b"authorization", f"Bearer {TOKEN}".encode()),
                          (b"content-type", b"application/json"),
                      ]}

    async def send(self, message):
        self.messages.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            self.first.set()
            if self.fail_send:
                raise OSError("synthetic disconnected socket")

    async def run(self):
        await self.app(self.scope, self.incoming.get, self.send)

    def events(self):
        data = b"".join(m.get("body", b"") for m in self.messages).decode()
        return [json.loads(line[6:]) for line in data.splitlines() if line.startswith("data: ")]

    @property
    def status(self):
        return next(m["status"] for m in self.messages if m["type"] == "http.response.start")


async def finish(exchange):
    await asyncio.wait_for(exchange.run(), 2)
    return exchange


async def test_read_sse_is_grounded_and_has_no_business_write():
    app, requests, drafts, audit = fixture()
    exchange = await finish(Exchange(app))
    assert exchange.status == 200
    events = exchange.events()
    assert events[0]["type"] == "run.started" and events[-1]["type"] == "run.completed"
    assert [e["cursor"] for e in events] == list(range(1, len(events) + 1))
    assert {e["run_id"] for e in events} == {requests[0].run_id}
    assert next(e for e in events if e["type"] == "message.delta")["payload"]["source_refs"] == [
        "synthetic-record@v1",
    ]
    headers = dict(exchange.messages[0]["headers"])
    assert headers[b"content-type"].startswith(b"text/event-stream")
    assert b"no-store" in headers[b"cache-control"] and headers[b"x-accel-buffering"] == b"no"
    assert drafts.committed_business_writes == 0 and audit.records[-1].outcome == "completed"


@pytest.mark.parametrize("mutation", ["token", "origin", "host", "duplicate", "remote", "missing"])
async def test_invalid_trust_boundary_never_starts_runtime(mutation):
    app, requests, _, _ = fixture()
    exchange = Exchange(app)
    headers = exchange.scope["headers"]
    if mutation == "remote":
        exchange.scope["client"] = ("192.0.2.1", 4567)
    elif mutation == "missing":
        exchange.scope["headers"] = [h for h in headers if h[0] != b"authorization"]
    elif mutation == "duplicate":
        headers.append((b"authorization", f"Bearer {TOKEN}".encode()))
    else:
        name = {"token": b"authorization", "origin": b"origin", "host": b"host"}[mutation]
        exchange.scope["headers"] = [(k, b"invalid" if k == name else v) for k, v in headers]
    await finish(exchange)
    assert exchange.status == 403 and not requests


@pytest.mark.parametrize("body,status", [
    ({"user_text": "synthetic", "route_mode": "read", "workspace_id": "other"}, 400),
    ({"user_text": "synthetic", "route_mode": "read", "requested_tools": ["system.sql"]}, 400),
    ({"user_text": "synthetic", "route_mode": "commit"}, 400),
    ({"user_text": "x" * 8001, "route_mode": "read"}, 400),
    (b"invalid-json", 400), (b"x" * 16385, 413),
    (b'{"user_text":"\\ud800","route_mode":"draft_write"}', 400),
])
async def test_bad_input_is_bounded_and_not_echoed(body, status):
    app, requests, _, _ = fixture()
    exchange = await finish(Exchange(app, body=body))
    assert exchange.status == status and not requests
    assert len(b"".join(m.get("body", b"") for m in exchange.messages)) < 100


@pytest.mark.parametrize("version,mode", [("2.3", "disconnect"), ("2.4", "cancel")])
async def test_first_feedback_and_disconnect_cleanup(version, mode):
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def model(messages, info):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    app, requests, _, audit = fixture(model)
    exchange = Exchange(app, body={"user_text": "synthetic", "route_mode": "answer_only"},
                        version=version)
    task = asyncio.create_task(exchange.run())
    try:
        await asyncio.wait_for(exchange.first.wait(), 1)
        await asyncio.wait_for(entered.wait(), 1)
        assert exchange.events()[0]["type"] == "run.started" and not audit.records
        if mode == "disconnect":
            exchange.incoming.put_nowait({"type": "http.disconnect"})
        else:
            task.cancel()
        try:
            await asyncio.wait_for(task, 1)
        except asyncio.CancelledError:
            pass
        assert cleaned.is_set() and audit.records[-1].outcome == "cancelled"
        assert app.state.active_streams == 0
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def test_send_failure_on_first_chunk_releases_slot():
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def model(messages, info):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    class FailedSocket(Exchange):
        async def send(self, message):
            await super().send(message)
            if message["type"] == "http.response.body" and message.get("body"):
                await asyncio.wait_for(entered.wait(), 1)
                raise OSError("synthetic socket failure while upstream is active")

    app, _, _, audit = fixture(model)
    await finish(FailedSocket(app, version="2.4", body={
        "user_text": "synthetic", "route_mode": "answer_only",
    }))
    assert cleaned.is_set() and audit.records[-1].outcome == "cancelled"
    assert app.state.active_streams == 0


async def test_replay_and_query_are_rejected_without_starting():
    app, requests, _, _ = fixture()
    exchange = Exchange(app)
    exchange.scope["headers"].append((b"last-event-id", b"1"))
    assert (await finish(exchange)).status == 409
    assert (await finish(Exchange(app, query=b"token=invalid"))).status == 400
    assert not requests


async def test_draft_is_uncommitted_and_server_owns_identifiers():
    app, requests, drafts, _ = fixture()
    exchange = await finish(Exchange(app, body={"user_text": "synthetic", "route_mode": "draft_write"}))
    draft = next(e for e in exchange.events() if e["type"] == "draft.available")["payload"]["draft"]
    assert draft["workspace_id"] == "synthetic" and draft["committed"] is False
    assert requests[0].requested_tools == frozenset({"task.draft"})
    assert drafts.committed_business_writes == 0


async def test_capacity_is_bounded_and_recovered_after_disconnect():
    release = asyncio.Event()

    async def model(messages, info):
        await release.wait()
        return ModelResponse(parts=[TextPart("synthetic")])

    app, requests, _, _ = fixture(model)
    exchanges = [Exchange(app, body={"user_text": "synthetic", "route_mode": "answer_only"})
                 for _ in range(4)]
    tasks = [asyncio.create_task(exchange.run()) for exchange in exchanges]
    try:
        await asyncio.wait_for(asyncio.gather(*(e.first.wait() for e in exchanges)), 1)
        assert app.state.active_streams == 4
        overflow = await finish(Exchange(app))
        assert overflow.status == 429 and len(requests) == 4
    finally:
        for exchange in exchanges:
            exchange.incoming.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(asyncio.gather(*tasks), 1)
    assert app.state.active_streams == 0
    release.set()
    assert (await finish(Exchange(app, body={
        "user_text": "synthetic", "route_mode": "answer_only",
    }))).events()[-1]["type"] == "run.completed"


async def test_chunked_request_limit_and_receive_timeout():
    app, requests, _, _ = fixture()
    exchange = Exchange(app)
    exchange.incoming.get_nowait()
    exchange.incoming.put_nowait({"type": "http.request", "body": b"x" * 10000, "more_body": True})
    exchange.incoming.put_nowait({"type": "http.request", "body": b"x" * 10000, "more_body": False})
    assert (await finish(exchange)).status == 413
    stalled = Exchange(app)
    stalled.incoming.get_nowait()
    assert (await finish(stalled)).status == 408
    assert not requests and app.state.active_streams == 0


async def test_model_fact_without_tool_fails_on_wire_not_success():
    app, _, _, _ = fixture(lambda messages, info: ModelResponse(parts=[TextPart("fabricated")]))
    exchange = await finish(Exchange(app))
    assert exchange.events()[-1]["type"] == "run.failed"
    assert all(e["type"] not in {"message.delta", "run.completed"} for e in exchange.events())


async def test_duplicate_json_keys_and_get_rejected_before_runtime():
    app, requests, _, _ = fixture()
    duplicate = b'{"user_text":"synthetic","route_mode":"read","route_mode":"draft_write"}'
    assert (await finish(Exchange(app, body=duplicate))).status == 400
    assert (await finish(Exchange(app, method="GET"))).status == 405
    assert not requests and app.state.active_streams == 0
