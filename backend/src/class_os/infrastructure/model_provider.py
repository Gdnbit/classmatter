"""Mature SDK construction only. Caller owns explicit client and its lifetime.

No credential storage or activation policy. Default runtime remains offline;
the explicit controller owns the configured client's async lifetime.
"""
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from class_os.application.model_configuration import ConfigurationRejected, ModelConfiguration, Protocol
from contextlib import asynccontextmanager
import logging
import httpx


def model_for_configuration(configuration, client):
    if (type(configuration) is not ModelConfiguration or not isinstance(client, AsyncOpenAI)
            or str(client.base_url).rstrip("/") != configuration.base_url.rstrip("/")
            or client.max_retries != 0 or client.organization or client.project):
        raise ConfigurationRejected()
    provider = OpenAIProvider(openai_client=client)
    if configuration.protocol is Protocol.CHAT:
        return OpenAIChatModel(configuration.model, provider=provider)
    return OpenAIResponsesModel(configuration.model, provider=provider, settings={"openai_store": False})


@asynccontextmanager
async def configured_client(configuration, key):
    # Application-controlled SDK diagnostics must not capture prompt/key data.
    for name in ("openai", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=8) as http:
        async with AsyncOpenAI(api_key=key.get_secret_value(), base_url=configuration.base_url,
                               organization="", project="", max_retries=0, http_client=http) as client:
            yield client
