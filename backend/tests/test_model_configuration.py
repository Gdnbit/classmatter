"""Pure candidate validation and SDK construction; never contacts a provider."""
import pytest
import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from sqlalchemy import text
from uuid import uuid4

from class_os.application.model_configuration import ModelConfiguration, Protocol, ConfigurationRejected
from class_os.infrastructure.model_provider import model_for_configuration
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings
from test_roster_gateway import roster
from test_identity import identity, PASSWORD


@pytest.mark.parametrize("body_type", ("ModelTestBody", "ModelEnableBody"))
@pytest.mark.parametrize("confirmation", (1, "true", False, None))
def test_model_network_confirmation_is_strict(body_type, confirmation):
    from class_os.interfaces.http import model_configuration as wire
    from pydantic import ValidationError
    values = {"candidate_id": str(uuid4()), "version": 1, "confirm_network": confirmation}
    if body_type == "ModelTestBody":
        values["request_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        getattr(wire, body_type).model_validate(values)


async def test_configured_client_is_explicit_no_network_and_always_closed(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from class_os.infrastructure import model_provider
    original = httpx.AsyncClient
    seen = []
    def client(**kwargs):
        seen.append(kwargs.copy())
        return original(**kwargs, transport=httpx.MockTransport(lambda request: pytest.fail("No request expected")))
    monkeypatch.setattr(model_provider, "httpx", SimpleNamespace(AsyncClient=client))
    monkeypatch.setenv("OPENAI_API_KEY", "unused-synthetic-env")
    config = ModelConfiguration(Protocol.CHAT, "synthetic", "https://provider.example.invalid/v1")
    with pytest.raises(RuntimeError, match="synthetic-abort"):
        async with model_provider.configured_client(config, SecretStr("synthetic-explicit")) as sdk:
            assert sdk.api_key == "synthetic-explicit" and sdk.max_retries == 0
            assert not sdk.organization and not sdk.project
            assert str(sdk.base_url) == config.base_url + "/"
            raise RuntimeError("synthetic-abort")
    assert sdk.is_closed()
    assert seen == [{"trust_env": False, "follow_redirects": False, "timeout": 8}]


@pytest.mark.parametrize("protocol", tuple(Protocol))
def test_model_configuration_is_explicit_nonsecret_candidate(protocol):
    config = ModelConfiguration(protocol, "synthetic-model-1", "https://provider.example.invalid/v1")
    assert config.protocol is protocol
    assert config.base_url == "https://provider.example.invalid/v1"


@pytest.mark.parametrize("protocol,model,url", [
    ("chat-completions", "synthetic", "https://provider.example.invalid/v1"),
    (Protocol.CHAT, "", "https://provider.example.invalid/v1"),
    (Protocol.CHAT, "a" * 129, "https://provider.example.invalid/v1"),
    (Protocol.CHAT, " model", "https://provider.example.invalid/v1"),
    (Protocol.CHAT, "model\nname", "https://provider.example.invalid/v1"),
    (Protocol.CHAT, "synthetic", "https://user:synthetic-secret@provider.example.invalid/v1"),
    (Protocol.CHAT, "synthetic", "https://provider.example.invalid/v1?api_key=synthetic-secret"),
    (Protocol.CHAT, "synthetic", "https://provider.example.invalid/v1#synthetic-secret"),
    (Protocol.CHAT, "synthetic", "http://provider.example.invalid/v1"),
    (Protocol.CHAT, "synthetic", "file:///synthetic"),
    (Protocol.CHAT, "synthetic", "https://provider.example.invalid:bad/v1"),
    (Protocol.CHAT, "synthetic", "https://provider.example.invalid/../v1"),
    (Protocol.CHAT, "synthetic", "https://provider.example.invalid/%61pi-key"),
    (Protocol.CHAT, "synthetic", "https://provider.example.invalid/v1\n"),
    (Protocol.CHAT, "synthetic", "https://provider.example.invalid\\@other.invalid/v1"),
    (Protocol.CHAT, "synthetic", "https://provider..invalid/v1"),
    (Protocol.CHAT, "synthetic", None),
])
def test_model_configuration_rejects_unknown_or_ambiguous_input_without_echo(protocol, model, url):
    with pytest.raises(ConfigurationRejected) as error:
        ModelConfiguration(protocol, model, url)
    assert str(error.value) == "Invalid model configuration"


def test_profile_does_not_load_environment_or_claim_endpoint_admission(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://must-not-contact.invalid/v1")
    config = ModelConfiguration(Protocol.RESPONSES, "synthetic", "http://127.0.0.1/v1")
    assert config.base_url == "http://127.0.0.1/v1"
    assert not hasattr(config, "api_key")


@pytest.mark.parametrize("protocol", tuple(Protocol))
async def test_sdk_factory_construction_sends_nothing_and_client_lifetime_is_explicit(protocol, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-must-not-inherit")
    monkeypatch.setenv("OPENAI_ORG_ID", "synthetic-must-not-inherit")
    def unexpected(request):
        pytest.fail("Construction must not probe network")
    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected), trust_env=False) as http:
        async with AsyncOpenAI(api_key="synthetic-explicit-key", base_url="http://127.0.0.1/v1",
                               organization="", project="", max_retries=0, http_client=http) as client:
            model = model_for_configuration(ModelConfiguration(protocol, "synthetic", "http://127.0.0.1/v1"), client)
            assert isinstance(model, OpenAIChatModel if protocol is Protocol.CHAT else OpenAIResponsesModel)
            assert model.model_name == "synthetic"
            assert not client.is_closed()
    assert client.is_closed()


@pytest.mark.parametrize("overrides", ({"max_retries": 2}, {"organization": "synthetic-org"},
                                    {"project": "synthetic-project"}, {"base_url": "http://127.0.0.1/other"}))
async def test_sdk_factory_rejects_hidden_scope_retries_and_endpoint_mismatch(overrides):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail("No network")), trust_env=False) as http:
        async with AsyncOpenAI(**{**dict(api_key="synthetic", base_url="http://127.0.0.1/v1", organization="",
                                        project="", max_retries=0, http_client=http), **overrides}) as client:
            with pytest.raises(ConfigurationRejected):
                model_for_configuration(ModelConfiguration(Protocol.CHAT, "synthetic", "http://127.0.0.1/v1"), client)


async def login(client):
    challenge = (await client.get("/api/identity/context")).json()
    headers = {"origin": "http://127.0.0.1:8000", "x-class-os-csrf": challenge["csrf_token"]}
    session = (await client.post("/api/identity/login", json={"password": PASSWORD}, headers=headers)).json()
    return {**headers, "x-class-os-csrf": session["csrf_token"]}, session["subject"]["workspace_id"]


@pytest.mark.db
async def test_configuration_http_is_authenticated_syntax_only_not_save_or_activation(roster):
    business, query, _, _, boundary, owner, _ = roster
    app = create_app(Settings(), identity=boundary, business=business, query=query)
    body = {"protocol": "responses", "model": "synthetic-model", "base_url": "https://provider.example.invalid/v1"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as client:
        headers, workspace = await login(client)
        path = f"/api/workspaces/{workspace}/agent/configuration/validate"
        assert (await client.post(path, json=body)).status_code == 403
        assert (await client.post(f"/api/workspaces/{uuid4()}/agent/configuration/validate", json=body, headers=headers)).status_code == 401
        for protocol in ("responses", "chat-completions"):
            reply = await client.post(path, json={**body, "protocol": protocol}, headers=headers)
            assert reply.status_code == 200
            assert reply.json() == {"schema_version": "class-os.model-configuration.v1", "status": "syntax-valid-not-enabled",
                                    "configuration": {**body, "protocol": protocol}, "persisted": False, "enabled": False, "network_tested": False}
        assert (await client.get(path, headers=headers)).status_code == 405
        for action in ("save", "activate", "test-network"):
            assert (await client.post(path.rsplit("/", 1)[0] + "/" + action, json=body, headers=headers)).status_code == 404
        for invalid in ({**body, "api_key": "synthetic-private-canary"}, {**body, "protocol": "auto"},
                        {**body, "enabled": True}, {**body, "base_url": "https://user:synthetic-private-canary@provider.invalid/v1"}):
            reply = await client.post(path, json=invalid, headers=headers)
            assert reply.status_code == 400 and "synthetic-private-canary" not in reply.text
    with owner.transaction(read_only=True) as connection:
        assert connection.execute(text("SELECT count(*) FROM class_os.command_proposal")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.manual_task")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action='class.context' AND outcome='allowed'")).scalar_one() >= 2


@pytest.mark.db
async def test_configuration_http_audit_outage_releases_no_candidate(roster, monkeypatch):
    business, query, _, _, boundary, _, _ = roster
    original = query.store.audit
    def failed(connection, binding, action, outcome, now, metadata):
        if action == "class.context":
            raise RuntimeError("synthetic-private-canary")
        return original(connection, binding, action, outcome, now, metadata)
    monkeypatch.setattr(query.store, "audit", failed)
    app = create_app(Settings(), identity=boundary, business=business, query=query)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://127.0.0.1:8000") as client:
        headers, workspace = await login(client)
        reply = await client.post(f"/api/workspaces/{workspace}/agent/configuration/validate", headers=headers,
                                  json={"protocol": "responses", "model": "synthetic", "base_url": "https://provider.invalid/v1"})
        assert reply.status_code == 503 and "configuration" not in reply.json()
        assert reply.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        assert "synthetic-private-canary" not in reply.text
