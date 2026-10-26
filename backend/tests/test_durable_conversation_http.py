"""Opt-in transport against actual ISB/QG/BCG/PG and original offline SDK."""
import asyncio
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, TextPart
from sqlalchemy import text

from class_os.application.conversation_worker import ConversationWorkerGateway
from class_os.application.roster import CommandRejected
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.durable_conversation import create_durable_app, SendBody, RenameBody, VersionBody, MessageContent
from class_os.interfaces.http.settings import Settings
from test_conversation_interaction_gateway import prepared
from test_conversation_control import control, storage, roster, identity


def setup(control, *, respond=None, timeout=10):
    value = prepared(control)
    value.worker = ConversationWorkerGateway(value.gateway.identity, value.store, clock=lambda: control[7][0])
    options = {}
    if respond is not None:
        from pydantic_ai.models.function import FunctionModel
        options["model_factory"] = lambda request: FunctionModel(respond)
    value.sdk = PydanticAgentRuntime(value.query, timeout=timeout, **options)
    value.app = create_durable_app(Settings(), worker=value.worker, query=value.query, sdk=value.sdk)
    value.base = f"/api/workspaces/{value.auth[3]}/conversation-d1/classes/{value.ids['class']}/terms/{value.ids['term']}"
    value.thread_path = value.base + f"/conversations/{value.thread}"
    value.headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": value.auth[2]}
    return value


def client(value, app=None):
    result = httpx.AsyncClient(transport=httpx.ASGITransport(app=app or value.app,
        client=("127.0.0.1", 12345), raise_app_exceptions=False), base_url="http://127.0.0.1:8000")
    for name, item in zip(("session", "client", "csrf"), value.auth[:3]):
        result.cookies.set("class_os_" + name, item, path="/api")
    return result


def send(key=None, mode="read"):
    return {"request_id": str(key or uuid4()), "text": "synthetic durable HTTP input", "mode": mode}


def test_transport_request_models_closed_and_no_dispatch_capabilities():
    good = send()
    assert SendBody.model_validate(good).mode == "read"
    for extra in ("generation", "lease_until", "sql", "approval", "draft_kind", "tools", "worker"):
        with pytest.raises(ValidationError):
            SendBody.model_validate({**good, extra: "synthetic-invalid"})
    for version in (True, "1", 0, -1, 2147483647):
        with pytest.raises(ValidationError):
            VersionBody.model_validate({"expected_version": version})
        with pytest.raises(ValidationError):
            RenameBody.model_validate({"request_id": str(uuid4()), "expected_version": version, "title": "synthetic title"})
    assert len(MessageContent(role="assistant", origin="assistant-unverified", text="x" * 8000).text) == 8000
    for role, origin, body in (("user", "assistant-unverified", "text"), ("assistant", "assistant-unverified", "文" * 6000)):
        with pytest.raises(ValidationError):
            MessageContent(role=role, origin=origin, text=body)


@pytest.mark.db
@pytest.mark.parametrize("mode", ["chat", "read", "draft"])
async def test_actual_http_persist_before_dispatch_and_rebuild_history(control, mode):
    value = setup(control)
    # Existing prepared thread is student-scoped; chat/task stay class-scoped.
    thread = uuid4()
    async with client(value) as api:
        created = await api.post(value.base + "/conversations", headers=value.headers,
            json={"thread_id": str(thread), "request_id": str(uuid4()), "title": "synthetic HTTP conversation"})
        assert created.status_code == 200, created.text
        path = value.base + f"/conversations/{thread}"
        body = send(mode=mode)
        queued = await api.post(path + "/turns", json=body, headers=value.headers)
        assert queued.status_code == 200, queued.text
        before = await api.get(path + "/turns/" + body["request_id"])
        assert before.status_code == 200 and before.json()["state"] == "queued"
        with control[4].transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='agent.run.started'")).scalar_one() == 0
        events = await api.post(path + "/turns/" + body["request_id"] + "/events", json={}, headers=value.headers)
        assert events.status_code == 200 and "event: run.completed" in events.text, events.text
        status = (await api.get(path + "/turns/" + body["request_id"])).json()
        assert status["state"] == "completed" and "generation" not in status and "lease_until" not in status
        replay = await api.post(path + "/turns/" + body["request_id"] + "/events", json={}, headers=value.headers)
        assert replay.status_code == 200 and replay.text == ""
        assert (await api.post(path + "/turns", json=body, headers=value.headers)).json() == queued.json()
        assert (await api.post(path + "/turns", json={**body, "text": "different input"}, headers=value.headers)).status_code == 409
    # Rebuild composition/SDK, keep only the actual database and protected root.
    sdk = PydanticAgentRuntime(value.query)
    app = create_durable_app(Settings(), worker=value.worker, query=value.query, sdk=sdk)
    async with client(value, app) as api:
        history = await api.get(path)
        assert history.status_code == 200, history.text
        data = history.json()
        assert (data["class_id"], data["term_id"], data["student_id"]) == (str(value.ids["class"]), str(value.ids["term"]), None)
        assert len(data["history"]["messages"]) == 2 and not data["history"]["truncated"]
        assert data["next_before"] is None and len(data["results"]) == 1
        result = data["results"][0]
        assert result["content_authority"] == "assistant-unverified" and result["draft_status"] == "uncommitted"
        assert bool(result["result"]["sources"]) == (mode == "read")
        assert (result["result"]["draft"] is not None) == (mode == "draft")
        assert history.headers["cache-control"] == "no-store" and not sdk.memory._items
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='agent.run.started'")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0


@pytest.mark.db
async def test_http_default_absence_scope_json_and_csrf_boundaries(control):
    value = setup(control)
    default = create_app(Settings(), identity=value.worker.identity, business=value.worker, query=value.query)
    async with client(value, default) as api:
        assert (await api.get(value.base + "/conversations")).status_code == 404
    async with client(value) as api:
        scoped = await api.get(value.thread_path)
        assert scoped.status_code == 200 and scoped.json()["student_id"] == str(value.ids["student"])
        assert (await api.post(value.thread_path + "/turns", json=send())).status_code == 403
        for wrong in (value.base.replace(str(value.auth[3]), str(uuid4())),
                      value.base.replace(str(value.ids["class"]), str(uuid4())),
                      value.base.replace(str(value.ids["term"]), str(uuid4()))):
            denied = await api.get(wrong + "/conversations")
            assert denied.status_code in (401, 409) and "合成人工会话" not in denied.text
        for body in ({**send(), "generation": str(uuid4())}, {**send(), "mode": "commit"}):
            assert (await api.post(value.thread_path + "/turns", json=body, headers=value.headers)).status_code == 400
        duplicated = '{"request_id":"%s","text":"one","text":"two","mode":"read"}' % uuid4()
        assert (await api.post(value.thread_path + "/turns", content=duplicated,
            headers={**value.headers, "content-type": "application/json"})).status_code == 400
        assert (await api.get(value.thread_path + "?before=1")).status_code == 400
        assert (await api.get(value.thread_path, headers={"origin": "https://untrusted.invalid"})).status_code == 403
        body = send()
        assert (await api.post(value.thread_path + "/turns", json=body, headers=value.headers)).status_code == 200
        assert (await api.post(value.thread_path + "/turns/" + body["request_id"] + "/events", json={},
            headers={**value.headers, "last-event-id": "1"})).status_code == 400
    with control[4].transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='agent.run.started'")).scalar_one() == 0


@pytest.mark.db
async def test_http_queued_cancel_and_expiry_never_start_sdk(control):
    calls = []
    def respond(messages, info):
        calls.append(True)
        return ModelResponse(parts=[TextPart("synthetic response")])
    value = setup(control, respond=respond)
    async with client(value) as api:
        body = send(mode="read")
        assert (await api.post(value.thread_path + "/turns", json=body, headers=value.headers)).status_code == 200
        status = (await api.get(value.thread_path + "/turns/" + body["request_id"])).json()
        cancelled = await api.post(value.thread_path + "/runs/" + status["run_id"] + "/cancel",
            json={"expected_version": status["version"]}, headers=value.headers)
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "read-status-required"
        events = await api.post(value.thread_path + "/turns/" + body["request_id"] + "/events", json={}, headers=value.headers)
        assert events.status_code == 200 and events.text == "" and not calls
        next_body = send()
        assert (await api.post(value.thread_path + "/turns", json=next_body, headers=value.headers)).status_code == 200
        control[7][0] += timedelta(minutes=1)
        events = await api.post(value.thread_path + "/turns/" + next_body["request_id"] + "/events", json={}, headers=value.headers)
        assert events.status_code == 200 and events.text == "" and not calls
        assert (await api.get(value.thread_path + "/turns/" + next_body["request_id"])).json()["state"] == "cancelled"


@pytest.mark.db
@pytest.mark.parametrize("fault", ["save", "timeout", "claim"])
async def test_http_fault_never_reports_persisted_completion(control, monkeypatch, fault):
    async def respond(messages, info):
        await asyncio.sleep(1)
        return ModelResponse(parts=[TextPart("synthetic answer must not leak")])
    value = setup(control, respond=respond if fault == "timeout" else None, timeout=.05 if fault == "timeout" else 10)
    body = send()
    async with client(value) as api:
        assert (await api.post(value.thread_path + "/turns", json=body, headers=value.headers)).status_code == 200
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic secret failure canary")
        if fault == "save":
            monkeypatch.setattr(value.worker, "finish_result", fail)
        elif fault == "claim":
            monkeypatch.setattr(value.worker, "claim", fail)
        response = await api.post(value.thread_path + "/turns/" + body["request_id"] + "/events", json={}, headers=value.headers)
        assert response.status_code == 200 and "event: run.failed" in response.text
        assert "event: run.completed" not in response.text and "event: message.delta" not in response.text
        assert "synthetic secret failure canary" not in response.text
        assert (await api.get(value.thread_path + "/turns/" + body["request_id"])).json()["state"] != "completed"


@pytest.mark.db
async def test_http_concurrent_dispatch_is_one_actual_sdk_and_gets_are_not_dispatch(control):
    calls = []
    async def respond(messages, info):
        calls.append(True)
        await asyncio.sleep(.05)
        return ModelResponse(parts=[TextPart("synthetic once-only answer")])
    value = setup(control, respond=respond)
    thread = uuid4()
    value.worker.create_conversation(*value.auth, value.ids["class"], value.ids["term"], thread, uuid4(), "synthetic concurrent send")
    path = value.base + f"/conversations/{thread}"
    body = send(mode="chat")
    async with client(value) as api:
        assert (await api.post(path + "/turns", json=body, headers=value.headers)).status_code == 200
        for _ in range(2):
            assert (await api.get(path)).status_code == 200
            assert (await api.get(value.base + "/conversations")).status_code == 200
            assert (await api.get(path + "/turns/" + body["request_id"])).json()["state"] == "queued"
        assert not calls
        endpoint = path + "/turns/" + body["request_id"] + "/events"
        responses = await asyncio.gather(*(api.post(endpoint, json={}, headers=value.headers) for _ in range(2)))
        assert all(response.status_code == 200 for response in responses)
        assert sum("event: run.completed" in response.text for response in responses) == 1 and len(calls) == 1
        assert sum("synthetic once-only answer" in response.text for response in responses) == 1
        with control[4].transaction(read_only=True) as connection:
            assert connection.execute(text("SELECT count(*) FROM class_os.conversation_message WHERE role='assistant'")).scalar_one() == 1


@pytest.mark.db
async def test_http_running_cancel_fences_late_completion(control):
    entered, finish = asyncio.Event(), asyncio.Event()
    async def respond(messages, info):
        entered.set()
        await finish.wait()
        return ModelResponse(parts=[TextPart("synthetic late answer must not leak")])
    value = setup(control, respond=respond)
    thread = uuid4()
    value.worker.create_conversation(*value.auth, value.ids["class"], value.ids["term"], thread, uuid4(), "synthetic late send")
    path = value.base + f"/conversations/{thread}"
    body = send(mode="chat")
    async with client(value) as api:
        assert (await api.post(path + "/turns", json=body, headers=value.headers)).status_code == 200
        response = asyncio.create_task(api.post(path + "/turns/" + body["request_id"] + "/events", json={}, headers=value.headers))
        try:
            await asyncio.wait_for(entered.wait(), 10)
            current = (await api.get(path + "/turns/" + body["request_id"])).json()
            assert current["state"] == "running"
            assert (await api.post(path + "/runs/" + current["run_id"] + "/cancel", json={"expected_version": current["version"]}, headers=value.headers)).status_code == 200
        finally:
            finish.set()
        result = await asyncio.wait_for(response, 10)
        assert "event: run.failed" in result.text and "event: run.completed" not in result.text
        assert "synthetic late answer must not leak" not in result.text
        assert (await api.get(path + "/turns/" + body["request_id"])).json()["state"] == "unknown"
        assert len((await api.get(path)).json()["history"]["messages"]) == 1


@pytest.mark.db
async def test_http_clear_requires_existing_x_approval_and_invalidates_old_history(control):
    value = setup(control)
    async with client(value) as api:
        body = send()
        await api.post(value.thread_path + "/turns", json=body, headers=value.headers)
        assert "event: run.completed" in (await api.post(value.thread_path + "/turns/" + body["request_id"] + "/events", json={}, headers=value.headers)).text
        old = (await api.get(value.thread_path)).json()["history"]
        preview = await api.post(value.thread_path + "/clear/preview", json={"expected_version": old["version"]}, headers=value.headers)
        assert preview.status_code == 200 and preview.json()["risk"] == "X", preview.text
        proposal = preview.json()
        base = f"/api/workspaces/{value.auth[3]}/commands"
        command = {"proposal_id": proposal["proposal_id"], "idempotency_key": str(uuid4())}
        assert (await api.post(base + "/commit", json=command, headers=value.headers)).status_code == 409
        approval = await api.post(base + "/approve", json={"proposal_id": proposal["proposal_id"], "payload_hash": proposal["payload_hash"]}, headers=value.headers)
        assert approval.status_code == 200
        result = await api.post(base + "/commit", json={**command, "approval": approval.json()["approval"]}, headers=value.headers)
        assert result.status_code == 200, result.text
        assert (await api.get(value.thread_path + f"/pages/{old['version']}/1")).status_code == 409
        cleared = await api.get(value.thread_path)
        assert cleared.status_code == 200 and cleared.json()["history"]["status"] == "cleared"
        assert not cleared.json()["history"]["messages"] and not cleared.json()["results"]


@pytest.mark.db
async def test_http_read_audit_failure_does_not_release_body(control, monkeypatch):
    value = setup(control)
    async with client(value) as api:
        monkeypatch.setattr(value.store, "audit", lambda *args: None)
        response = await api.get(value.thread_path)
        assert response.status_code == 503 and "合成人工会话" not in response.text
