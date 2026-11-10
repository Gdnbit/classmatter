"""Native Gemini tool signatures and transport boundaries; entirely offline."""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace
from pathlib import Path
import subprocess
import sys

import httpx
from openai import AsyncOpenAI
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.usage import UsageLimits
import pytest

from class_os.domain.model_configuration import ConfigurationRejected, ModelConfiguration, Protocol, validate_model_proxy
from class_os.infrastructure import model_provider
from class_os.interfaces.http.settings import Settings
from test_roster_gateway import roster
from test_identity import identity

CONFIG = ModelConfiguration(Protocol.CHAT, "gemini-3.1-flash-lite", model_provider.GOOGLE_COMPAT_BASE)
KEY = "synthetic-google-provider-canary"
SIGNATURE = "c3ludGhldGljLXNpZ25hdHVyZQ=="


@pytest.mark.parametrize('effort', ['low', 'medium', 'high'])
async def test_composer_effort_reaches_native_google_wire(monkeypatch, effort):
    from class_os.infrastructure.reasoning import reasoning_settings
    calls = []
    def reply(request):
        body = json.loads(request.content); calls.append(body)
        assert body['generationConfig']['thinkingConfig']['thinking_level'] == effort.upper()
        return httpx.Response(200, json=packet([{'text': 'OK'}]))
    intercept(monkeypatch, reply)
    async with model_provider.configured_client(CONFIG, SecretStr(KEY)) as session:
        model = model_provider.model_for_configuration(CONFIG, session)
        result = await Agent(model, model_settings=reasoning_settings(model, effort)).run('Synthetic effort probe')
        assert result.output == 'OK'
    assert len(calls) == 1


def intercept(monkeypatch, handler):
    original = httpx.AsyncClient
    clients, options = [], []
    def create(**kwargs):
        options.append(kwargs.copy())
        client = original(**kwargs, transport=httpx.MockTransport(handler))
        clients.append(client)
        return client
    monkeypatch.setattr(model_provider, "httpx", SimpleNamespace(AsyncClient=create))
    return clients, options


def packet(parts):
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
            "modelVersion": CONFIG.model,
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}}


async def test_native_tool_roundtrip_preserves_signature_and_closes_without_business_writes(monkeypatch, caplog):
    requests, calls = [], []
    def reply(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.path == "/v1beta/models/gemini-3.1-flash-lite:generateContent"
        assert request.headers["x-goog-api-key"] == KEY
        assert request.headers["x-server-timeout"] == "30"
        assert request.extensions['timeout']['read'] == 30
        body = json.loads(request.content)
        assert body["generationConfig"]["thinkingConfig"] == {"thinking_level": "MINIMAL"}
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, json=packet([{"functionCall": {"name": "synthetic_probe", "args": {}},
                                                   "thoughtSignature": SIGNATURE}]))
        parts = [p for content in body["contents"] for p in content["parts"]]
        assert any(p.get("thoughtSignature") == SIGNATURE and "functionCall" in p for p in parts)
        assert any("functionResponse" in p for p in parts)
        return httpx.Response(200, json=packet([{"text": "OK"}]))
    clients, options = intercept(monkeypatch, reply)
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-must-not-inherit")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-must-not-inherit")
    def synthetic_probe() -> str:
        """Read a fixed synthetic value, without any external side effect."""
        calls.append(True)
        return "synthetic-only"
    async with model_provider.configured_client(CONFIG, SecretStr(KEY)) as session:
        agent = Agent(model_provider.model_for_configuration(CONFIG, session), tools=[synthetic_probe], retries=0)
        agent.instrument = False
        result = await agent.run("Call synthetic_probe once and reply OK", usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1))
        assert result.output == "OK" and result.usage.requests == 2
    assert len(calls) == 1 and len(requests) == 2
    assert clients[0].is_closed and session.closed
    assert options == [{"trust_env": False, "follow_redirects": False, "timeout": 30}]
    assert KEY not in caplog.text
    with pytest.raises(ConfigurationRejected):
        model_provider.model_for_configuration(CONFIG, session)


@pytest.mark.parametrize("status", [302, 429, 503])
async def test_native_no_redirect_or_automatic_retry(status, monkeypatch):
    calls = []
    def reply(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://must-not-contact.invalid/v1"},
                              json={"error": {"code": status, "status": "UNAVAILABLE", "message": "synthetic failure"}})
    clients, _ = intercept(monkeypatch, reply)
    with pytest.raises(Exception):
        async with model_provider.configured_client(CONFIG, SecretStr(KEY)) as session:
            agent = Agent(model_provider.model_for_configuration(CONFIG, session), retries=0)
            agent.instrument = False
            await agent.run("Synthetic only", usage_limits=UsageLimits(request_limit=1))
    assert len(calls) == 1 and clients[0].is_closed and session.closed


async def test_native_cancellation_closes_client_without_followup(monkeypatch):
    entered = asyncio.Event()
    calls = []
    async def reply(request):
        calls.append(request)
        entered.set()
        await asyncio.Event().wait()
    clients, _ = intercept(monkeypatch, reply)
    async def run():
        async with model_provider.configured_client(CONFIG, SecretStr(KEY)) as session:
            await Agent(model_provider.model_for_configuration(CONFIG, session), retries=0).run("Synthetic only")
    task = asyncio.create_task(run())
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) == 1 and clients[0].is_closed


@pytest.mark.parametrize('base,model,deadline', [
    ('https://open.bigmodel.cn/api/paas/v4/', 'glm-4-flash-250414', 30),
    ('https://open.bigmodel.cn/api/paas/v4/', 'synthetic-other-model', 8),
    ('https://fixture.invalid/v1/', 'glm-4-flash-250414', 8),
])
async def test_registered_free_profile_has_bounded_wire_timeout_without_retry(monkeypatch, base, model, deadline):
    requests = []
    def reply(request):
        requests.append(request)
        assert request.extensions['timeout']['read'] == deadline
        return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1, 'model': model,
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'OK'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    clients, options = intercept(monkeypatch, reply)
    configuration = ModelConfiguration(Protocol.CHAT, model, base)
    async with model_provider.configured_client(configuration, SecretStr(KEY)) as client:
        assert client.max_retries == 0
        agent = Agent(model_provider.model_for_configuration(configuration, client), retries=0)
        agent.instrument = False
        assert (await agent.run('Synthetic only')).output == 'OK'
    assert len(requests) == 1 and clients[0].is_closed and options[0]['timeout'] == deadline


async def test_sdk_auto_continuation_cannot_dispatch_outside_agent_budget(monkeypatch):
    calls = []
    def reply(request):
        calls.append(request)
        value = packet([{"text": "incomplete synthetic answer"}])
        value["candidates"][0].update(finishReason="CONTINUATION", continuationToken=SIGNATURE)
        return httpx.Response(200, json=value)
    clients, _ = intercept(monkeypatch, reply)
    with pytest.raises(ConfigurationRejected):
        async with model_provider.configured_client(CONFIG, SecretStr(KEY)) as session:
            await Agent(model_provider.model_for_configuration(CONFIG, session), retries=0).run(
                "Synthetic only", usage_limits=UsageLimits(request_limit=1))
    assert len(calls) == 1 and clients[0].is_closed


async def test_google_rejects_wrong_protocol_client_binding_and_openai_fallback(monkeypatch):
    clients, _ = intercept(monkeypatch, lambda r: pytest.fail("No network expected"))
    with pytest.raises(ConfigurationRejected):
        async with model_provider.configured_client(replace(CONFIG, protocol=Protocol.RESPONSES), SecretStr(KEY)):
            pytest.fail("Rejected before constructing SDK")
    assert clients == []
    for candidate, secret in [(replace(CONFIG, model="gemini-../other"), SecretStr(KEY)), (CONFIG, SecretStr(""))]:
        with pytest.raises(ConfigurationRejected):
            async with model_provider.configured_client(candidate, secret):
                pytest.fail("Invalid native configuration must not inherit ambient credentials")
    assert clients == []
    async with model_provider.configured_client(CONFIG, SecretStr(KEY)) as session:
        with pytest.raises(ConfigurationRejected):
            model_provider.model_for_configuration(replace(CONFIG, model="other-model"), session)
    async with AsyncOpenAI(api_key=KEY, base_url=CONFIG.base_url, max_retries=0, organization="", project="") as client:
        with pytest.raises(ConfigurationRejected):
            model_provider.model_for_configuration(CONFIG, client)


@pytest.mark.parametrize("proxy", ["http://remote.invalid:7890", "http://localhost:7890", "https://127.0.0.1:7890",
    "http://user:secret@127.0.0.1:7890", "http://127.0.0.1:0", "http://127.0.0.1:65536", "http://127.0.0.1:07890",
    "http://127.0.0.1:7890/", "http://127.0.0.1:7890?key=secret", "", False, 7890])
def test_proxy_is_explicit_canonical_loopback_only(proxy):
    with pytest.raises(ConfigurationRejected) as error:
        Settings(model_api_proxy=proxy)
    assert str(error.value) == "Invalid model configuration"


def test_proxy_default_is_off_and_never_loaded_from_environment():
    assert validate_model_proxy(None) is None
    assert Settings.from_env({"HTTPS_PROXY": "http://remote.invalid:7890", "CLASS_OS_MODEL_API_PROXY": "http://127.0.0.1:7890"}).model_api_proxy is None
    assert Settings(model_api_proxy="http://127.0.0.1:7890").model_api_bases == ()


def test_operator_proxy_flag_is_refused_for_read_only_doctor_before_runtime_import():
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'local.py'),
                             'doctor', '--model-api-proxy', 'http://127.0.0.1:7890'],
                            capture_output=True, timeout=5)
    assert result.returncode == 2 and b'only accepted for serve' in result.stderr


async def test_explicit_proxy_reaches_transport_without_authorizing_endpoint(monkeypatch):
    clients, options = intercept(monkeypatch, lambda r: pytest.fail("Construction must not call network"))
    async with model_provider.configured_client(CONFIG, SecretStr(KEY), proxy="http://127.0.0.1:7890"):
        pass
    assert options[0]["proxy"] == "http://127.0.0.1:7890" and clients[0].is_closed


@pytest.mark.db
async def test_google_uses_existing_bcg_configuration_proof_qg_and_audit(roster, monkeypatch):
    from uuid import uuid4
    from sqlalchemy import text
    from class_os.application.agent import AgentRequest, Mode
    from class_os.infrastructure.agent import PydanticAgentRuntime
    from class_os.infrastructure.model_control import ModelController
    from class_os.infrastructure.model_secrets import ModelSecrets
    from test_model_secrets import fixture_codec
    from test_activity_gateway import seed
    business, query, _, auth, _, owner, clock = roster
    seed(roster)
    calls = []
    def reply(request):
        body = json.loads(request.content)
        calls.append(body)
        if any('functionResponse' in part for part in body['contents'][-1]['parts']):
            return httpx.Response(200, json=packet([{'text': 'OK'}]))
        tool = body['tools'][0]['functionDeclarations'][0]['name']
        assert tool in {'class_os_probe', 'attention_list'}
        return httpx.Response(200, json=packet([{'functionCall': {'name': tool, 'args': {}}, 'thoughtSignature': SIGNATURE}]))
    clients, _ = intercept(monkeypatch, reply)
    vault = ModelSecrets(fixture_codec, clock=lambda: clock[0])
    business.store.model_secrets = vault
    runtime = PydanticAgentRuntime(query)
    controller = ModelController(query, vault, runtime, allowed_bases=(CONFIG.base_url,), clock=lambda: clock[0])
    command = vault.stage(auth, CONFIG, KEY, 0)
    proposal = business.preview(*auth, command)
    approval = business.approve(*auth, proposal.proposal_id, proposal.payload_hash)
    business.commit(*auth, proposal.proposal_id, uuid4(), approval)
    assert (await controller.status(auth))['mode'] == 'offline' and not calls
    with pytest.raises(ConfigurationRejected):
        await controller.enable(auth, command.candidate_id, 1)
    assert await controller.test(auth, command.candidate_id, 1, uuid4())
    await controller.enable(auth, command.candidate_id, 1)
    runtime.model_context = controller.context
    conversation = runtime.conversation(auth)
    events = [event async for event in runtime.stream(auth, AgentRequest(conversation.conversation_id, 'Synthetic current work', Mode.READ))]
    assert events[-1].type == 'run.completed' and len(calls) == 4
    assert next(e for e in events if e.type == 'message.delta').payload['source_refs']
    assert all(client.is_closed for client in clients)
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text('SELECT count(*) FROM class_os.manual_task')).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='agent.run.completed'")).scalar_one() == 1
    await controller.disable(auth)
    assert (await controller.status(auth))['mode'] == 'offline'
