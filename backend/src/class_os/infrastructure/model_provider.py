"""Mature SDK construction only. Caller owns explicit client and its lifetime.

No credential storage or activation policy. Default runtime remains offline;
the explicit controller owns the configured client's async lifetime.
"""
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from dataclasses import dataclass, field

from class_os.domain.model_configuration import ConfigurationRejected, ModelConfiguration, Protocol, validate_model_proxy
from contextlib import asynccontextmanager
import logging
import json
import re
import httpx

GOOGLE_COMPAT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
GOOGLE_NATIVE_BASE = "https://generativelanguage.googleapis.com/"


@dataclass
class NativeGoogleSession:
    configuration: ModelConfiguration
    provider: object = field(repr=False)
    closed: bool = False


def _google_configuration(configuration):
    return configuration.base_url.rstrip("/") == GOOGLE_COMPAT_BASE.rstrip("/")


async def _google_request_boundary(request):
    # Recent Google SDKs may auto-continue generation outside the Agent's
    # request/token accounting. Reject that extra dispatch before any bytes go
    # to the network; the original result stays incomplete, never a success.
    if (request.url.scheme != "https" or request.url.host != "generativelanguage.googleapis.com"
            or request.url.port not in (None, 443) or request.method != "POST"):
        raise ConfigurationRejected()
    body = json.loads(request.content)
    if "continuationToken" in body:
        raise ConfigurationRejected()


def model_for_configuration(configuration, client):
    if type(configuration) is not ModelConfiguration:
        raise ConfigurationRejected()
    if _google_configuration(configuration):
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider
        if (configuration.protocol is not Protocol.CHAT or re.fullmatch(r"gemini-[A-Za-z0-9][A-Za-z0-9._-]{0,100}", configuration.model) is None
                or type(client) is not NativeGoogleSession
                or client.closed or client.configuration != configuration
                or not isinstance(client.provider, GoogleProvider)
                or str(client.provider.base_url).rstrip("/") != GOOGLE_NATIVE_BASE.rstrip("/")):
            raise ConfigurationRejected()
        # Use the SDK's native message protocol: the compatible API adapter does
        # not preserve Gemini tool thought signatures. Never forge a signature.
        return GoogleModel(configuration.model, provider=client.provider)
    if (not isinstance(client, AsyncOpenAI)
            or str(client.base_url).rstrip("/") != configuration.base_url.rstrip("/")
            or client.max_retries != 0 or client.organization or client.project):
        raise ConfigurationRejected()
    provider = OpenAIProvider(openai_client=client)
    if configuration.protocol is Protocol.CHAT:
        return OpenAIChatModel(configuration.model, provider=provider)
    return OpenAIResponsesModel(configuration.model, provider=provider, settings={"openai_store": False})


@asynccontextmanager
async def configured_client(configuration, key, *, proxy=None):
    proxy = validate_model_proxy(proxy)
    if type(configuration) is not ModelConfiguration:
        raise ConfigurationRejected()
    if _google_configuration(configuration) and (configuration.protocol is not Protocol.CHAT
            or re.fullmatch(r"gemini-[A-Za-z0-9][A-Za-z0-9._-]{0,100}", configuration.model) is None
            or not key.get_secret_value()):
        raise ConfigurationRejected()
    # Application-controlled SDK diagnostics must not capture prompt/key data.
    for name in ("openai", "httpx", "httpcore", "httpx2", "httpcore2", "google.genai", "google_genai"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    transport = {"proxy": proxy} if proxy is not None else {}
    # Google rejects explicitly advertised request deadlines below 10 seconds;
    # controller/runtime outer budgets remain unchanged and can cancel sooner.
    timeout = 10 if _google_configuration(configuration) else 8
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=timeout, **transport) as http:
        if _google_configuration(configuration):
            http.event_hooks["request"].append(_google_request_boundary)
            from google.genai.types import HttpRetryOptions
            from pydantic_ai.providers.google import GoogleProvider
            provider = GoogleProvider(api_key=key.get_secret_value(), base_url=GOOGLE_NATIVE_BASE,
                                      http_client=http, retry_options=HttpRetryOptions(attempts=1))
            session = NativeGoogleSession(configuration, provider)
            try:
                yield session
            finally:
                session.closed = True
                try:
                    await provider.client.aio.aclose()
                finally:
                    provider.client.close()
            return
        async with AsyncOpenAI(api_key=key.get_secret_value(), base_url=configuration.base_url,
                               organization="", project="", max_retries=0, http_client=http) as client:
            yield client
