from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4
import asyncio

import httpx
from openai import AsyncOpenAI
import pytest
from sqlalchemy import text

from class_os.application.agent import AgentRequest, AgentRejected, Mode
from class_os.application.roster import CommandRejected
from class_os.domain.model_configuration import ConfigurationRejected, ModelConfiguration, Protocol
from class_os.domain.model_control import ModelControl
from class_os.domain.roster import decode
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.model_control import ModelController
from class_os.infrastructure.model_secrets import ModelSecrets
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_activity_gateway import seed
from test_roster_gateway import roster
from test_identity import identity
from test_model_configuration import login
from test_model_secrets import fixture_codec
from test_agent_api_protocol import protocol_reply, MODEL


URL = "https://provider.example.invalid/v1"
KEY = "synthetic-model-control-canary"


@pytest.fixture
def controlled(roster):
    business, query, _, credentials, _, _, clock = roster
    vault = ModelSecrets(fixture_codec, clock=lambda: clock[0])
    business.store.model_secrets = vault
    runtime = PydanticAgentRuntime(query)
    calls, clients = [], []
    faults = {"value": None, "entered": asyncio.Event()}
    @asynccontextmanager
    async def factory(profile, key):
        async def reply(request):
            assert request.headers["authorization"] == "Bearer " + KEY
            calls.append(request)
            import json
            if faults["value"] == "http-error":
                return httpx.Response(503, json={"error": {"message": "synthetic-private-provider-error"}})
            if faults["value"] == "cancel":
                faults["entered"].set()
                await asyncio.sleep(30)
            if faults["value"] == "rotate":
                faults["value"] = None
                clear = ModelControl("model_configuration.clear", uuid4(), 1)
                proposal = business.preview(*credentials, clear)
                approval = business.approve(*credentials, proposal.proposal_id, proposal.payload_hash)
                business.commit(*credentials, proposal.proposal_id, uuid4(), approval)
            packet = protocol_reply(profile.protocol.value, json.loads(request.content), len(calls), malicious=faults["value"] == "unknown-tool")
            if faults["value"] == "truncated":
                if profile.protocol is Protocol.CHAT:
                    packet["choices"][0]["finish_reason"] = "length"
                else:
                    packet.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
            return httpx.Response(200, json=packet)
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply), trust_env=False, follow_redirects=False) as http:
            async with AsyncOpenAI(api_key=key.get_secret_value(), base_url=profile.base_url,
                                   organization="", project="", max_retries=0, http_client=http) as client:
                clients.append(client)
                yield client
    controller = ModelController(query, vault, runtime, allowed_bases=(URL,), client_factory=factory, clock=lambda: clock[0])
    runtime.model_context = controller.context
    runtime.provider_state = controller.label
    return controller, vault, runtime, calls, clients, faults


def save(roster, vault, protocol=Protocol.CHAT):
    business, _, _, auth, _, _, _ = roster
    command = vault.stage(auth, ModelConfiguration(protocol, MODEL, URL), KEY, 0)
    proposal = business.preview(*auth, command)
    assert proposal.risk == "W2"
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    key = uuid4()
    receipt = business.commit(*auth, proposal.proposal_id, key, approval)
    assert receipt == business.commit(*auth, proposal.proposal_id, key, approval)
    return command, receipt


@pytest.mark.db
def test_model_configuration_bcg_approval_cas_and_atomic_audit_failure(roster, controlled, monkeypatch):
    controller, vault, _, calls, _, _ = controlled
    business, query, _, auth, _, owner, _ = roster
    command = vault.stage(auth, ModelConfiguration(Protocol.CHAT, MODEL, URL), KEY, 0)
    proposal = business.preview(*auth, command)
    with pytest.raises(CommandRejected):
        business.commit(*auth, proposal.proposal_id, uuid4())
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    original = business.store.audit
    def fault(connection, binding, action, outcome, now, metadata):
        if action == "command.commit" and outcome == "allowed":
            raise RuntimeError("synthetic-audit-outage")
        return original(connection, binding, action, outcome, now, metadata)
    monkeypatch.setattr(business.store, "audit", fault)
    key = uuid4()
    with pytest.raises(RuntimeError):
        business.commit(*auth, proposal.proposal_id, key, approval)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.model_configuration")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.command_receipt")).scalar_one() == 0
        assert KEY not in str(connection.execute(text("SELECT payload FROM class_os.command_proposal")).all())
    monkeypatch.setattr(business.store, "audit", original)
    receipt = business.commit(*auth, proposal.proposal_id, key, approval)
    assert receipt.version == 1
    with pytest.raises(CommandRejected):
        business.preview(*auth, command)
    with owner.transaction(read_only=True) as connection:
        assert KEY.encode() not in connection.execute(text("SELECT sealed FROM class_os.model_configuration")).scalar_one()
    assert calls == []


@pytest.mark.db
@pytest.mark.parametrize("protocol", tuple(Protocol))
async def test_model_test_enable_runtime_disable_and_no_secret_in_exit(roster, controlled, protocol):
    controller, vault, runtime, calls, clients, _ = controlled
    business, query, _, auth, _, _, clock = roster
    seed(roster)
    command, receipt = save(roster, vault, protocol)
    with pytest.raises(ConfigurationRejected):
        await controller.enable(auth, command.candidate_id, 1)
    request_id = uuid4()
    assert await controller.test(auth, command.candidate_id, 1, request_id)
    assert len(calls) == 2
    assert await controller.test(auth, command.candidate_id, 1, request_id)
    assert len(calls) == 2, "Same test request must not trigger another paid attempt"
    old = runtime.conversation(auth)
    await controller.enable(auth, command.candidate_id, 1)
    with pytest.raises(AgentRejected):
        runtime.prepare(auth, AgentRequest(old.conversation_id, "synthetic", Mode.READ))
    conversation = runtime.conversation(auth)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, "synthetic", Mode.READ))]
    assert events[-1].type == "run.completed", runtime.last_failure_type
    assert any(event.type == "message.delta" and event.payload["source_refs"] for event in events)
    assert len(calls) == 4 and all(client.is_closed() for client in clients)
    await controller.disable(auth)
    assert (await controller.status(auth))["mode"] == "offline"
    assert runtime.memory._items == {}
    from class_os.domain.exit_package import CreateExitExport, validate_package
    summary = query.exit_summary(*auth)
    export = business.preview(*auth, CreateExitExport(uuid4(), summary.core_hash))
    approval = business.approve(*auth, export.proposal_id, export.payload_hash)
    downloaded = business.commit(*auth, export.proposal_id, uuid4(), approval)
    artifact = query.exit_download(*auth, downloaded.resource_id)
    validate_package(artifact.bundle)
    assert KEY not in str(artifact.bundle) and "model_configuration" not in artifact.bundle["core"]
    replacement = runtime.conversation(auth)
    events = [event async for event in runtime.stream(auth, AgentRequest(replacement.conversation_id, "synthetic", Mode.READ))]
    assert events[-1].type == "run.completed" and len(calls) == 4
    clear = ModelControl("model_configuration.clear", uuid4(), 1)
    proposal = business.preview(*auth, clear)
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    assert business.commit(*auth, proposal.proposal_id, uuid4(), approval).version == 2
    status = await controller.status(auth)
    assert status["configuration"] is None and not status["key_configured"]
    assert KEY not in str(status)


@pytest.mark.db
async def test_model_controls_default_no_egress_and_http_secret_never_returned(roster, controlled):
    controller, vault, runtime, calls, _, _ = controlled
    business, query, _, auth, boundary, owner, _ = roster
    controller.allowed_bases = ()
    app = create_app(Settings(), identity=boundary, business=business, query=query, agent=runtime, model_controller=controller)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        headers, workspace = await login(client)
        base = f"/api/workspaces/{workspace}/agent/configuration"
        body = {"protocol": "responses", "model": MODEL, "base_url": URL, "api_key": KEY, "expected_version": 0}
        assert (await client.post(base + "/stage", json=body)).status_code == 403
        staged = await client.post(base + "/stage", json=body, headers=headers)
        assert staged.status_code == 200 and KEY not in staged.text
        command = staged.json()["command"]
        preview = await client.post(f"/api/workspaces/{workspace}/commands/preview", json=command, headers=headers)
        assert preview.status_code == 200 and KEY not in preview.text
        value = preview.json()
        approved = (await client.post(f"/api/workspaces/{workspace}/commands/approve", json={"proposal_id": value["proposal_id"], "payload_hash": value["payload_hash"]}, headers=headers)).json()
        receipt = await client.post(f"/api/workspaces/{workspace}/commands/commit", json={"proposal_id": value["proposal_id"], "idempotency_key": str(uuid4()), "approval": approved["approval"]}, headers=headers)
        assert receipt.status_code == 200 and KEY not in receipt.text
        status = await client.get(base + "/status")
        assert status.status_code == 200 and status.json()["key_configured"] and not status.json()["network_permitted"]
        assert KEY not in status.text and "sealed" not in status.text
        request = {"candidate_id": command["candidate_id"], "version": 1, "request_id": str(uuid4()), "confirm_network": True}
        assert (await client.post(base + "/test", json=request, headers=headers)).status_code == 400
    assert calls == []


@pytest.mark.db
@pytest.mark.parametrize("fault", ("http-error", "unknown-tool", "truncated"))
async def test_failed_protocol_probe_cannot_enable_or_retry_same_request(roster, controlled, fault):
    controller, vault, runtime, calls, clients, faults = controlled
    auth = roster[3]
    command, _ = save(roster, vault)
    faults["value"] = fault
    request_id = uuid4()
    assert not await controller.test(auth, command.candidate_id, 1, request_id)
    before = len(calls)
    assert not await controller.test(auth, command.candidate_id, 1, request_id)
    assert len(calls) == before and before <= 2
    with pytest.raises(ConfigurationRejected):
        await controller.enable(auth, command.candidate_id, 1)
    assert (await controller.status(auth))["mode"] == "offline"
    assert all(client.is_closed() for client in clients)


@pytest.mark.db
async def test_cancelled_probe_releases_slot_closes_client_and_keeps_offline(roster, controlled):
    controller, vault, runtime, calls, clients, faults = controlled
    auth = roster[3]
    command, _ = save(roster, vault)
    faults["value"] = "cancel"
    request_id = uuid4()
    running = asyncio.create_task(controller.test(auth, command.candidate_id, 1, request_id))
    await asyncio.wait_for(faults["entered"].wait(), 3)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert not controller._testing and all(client.is_closed() for client in clients)
    assert not await controller.test(auth, command.candidate_id, 1, request_id)
    assert len(calls) == 1


@pytest.mark.db
async def test_inflight_configuration_change_releases_no_answer_or_history(roster, controlled):
    controller, vault, runtime, calls, _, faults = controlled
    auth = roster[3]
    seed(roster)
    command, _ = save(roster, vault)
    assert await controller.test(auth, command.candidate_id, 1, uuid4())
    await controller.enable(auth, command.candidate_id, 1)
    faults["value"] = "rotate"
    conversation = runtime.conversation(auth)
    events = [item async for item in runtime.stream(auth, AgentRequest(conversation.conversation_id, "synthetic", Mode.READ))]
    assert events[-1].type == "run.failed"
    assert not any(item.type in ("message.delta", "draft.available") for item in events)
    assert conversation.history == [] and runtime.active == 0
    assert (await controller.status(auth))["mode"] == "stale"


@pytest.mark.db
def test_suppressed_model_mutation_cannot_issue_success_receipt(roster, controlled):
    _, vault, _, _, _, _ = controlled
    business, _, _, auth, _, owner, _ = roster
    command = vault.stage(auth, ModelConfiguration(Protocol.CHAT, MODEL, URL), KEY, 0)
    proposal = business.preview(*auth, command)
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    with owner.transaction() as connection:
        connection.execute(text("CREATE FUNCTION class_os.skip_model_fixture() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN NULL; END'"))
        connection.execute(text("CREATE TRIGGER skip_model_fixture BEFORE INSERT ON class_os.model_configuration FOR EACH ROW EXECUTE FUNCTION class_os.skip_model_fixture()"))
    with pytest.raises(RuntimeError):
        business.commit(*auth, proposal.proposal_id, uuid4(), approval)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.model_configuration")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.command_receipt")).scalar_one() == 0
