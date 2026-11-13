"""SDK wire round-trip for the opt-in free profile; no external requests."""
import json
from typing import Literal

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from class_os.domain.model_configuration import ModelConfiguration, Protocol
from class_os.infrastructure.model_provider import model_for_configuration, request_timeout


@pytest.mark.parametrize('base,model,disabled', [
    ('https://open.bigmodel.cn/api/paas/v4/', 'glm-4.7-flash', True),
    ('https://open.bigmodel.cn/api/paas/v4/', 'glm-4-flash-250414', False),
    ('https://open.bigmodel.cn/api/paas/v4/', 'glm-4.7-flashx', False),
    ('https://fixture.invalid/v1/', 'glm-4.7-flash', False),
])
async def test_free_profile_sdk_preserves_real_tool_roundtrip_and_other_model_defaults(base, model, disabled):
    requests, calls = [], []
    def reply(request):
        body = json.loads(request.content); requests.append(body)
        assert body['model'] == model and body['max_completion_tokens'] == 512 and 'max_tokens' not in body
        assert body.get('thinking') == ({'type': 'disabled'} if disabled else None)
        assert len(body['tools']) == 1 and body['tools'][0]['function']['name'] == 'synthetic_probe'
        if len(requests) == 1:
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'probe-1', 'type': 'function', 'function': {'name': 'synthetic_probe', 'arguments': '{"scope":"synthetic"}'}}]}
        else:
            assert body['messages'][-1]['role'] == 'tool' and body['messages'][-1]['tool_call_id'] == 'probe-1'
            assert json.loads(body['messages'][-1]['content']) == {'fixture_number': 7}
            message = {'role': 'assistant', 'content': '7'}
        return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1, 'model': model,
            'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if len(requests) == 1 else 'stop'}],
            'usage': {'prompt_tokens': 20, 'completion_tokens': 5, 'total_tokens': 25}})
    async def synthetic_probe(scope: Literal['synthetic']) -> dict:
        """Read a synthetic fixture; no business data or writes."""
        calls.append(scope); return {'fixture_number': 7}
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply), trust_env=False) as http:
        async with AsyncOpenAI(api_key='synthetic-only', base_url=base, organization='', project='', max_retries=0, http_client=http) as client:
            configuration = ModelConfiguration(Protocol.CHAT, model, base)
            assert request_timeout(configuration) == (30 if base == 'https://open.bigmodel.cn/api/paas/v4/' and model in ('glm-4-flash-250414', 'glm-4.7-flash') else 8)
            agent = Agent(model_for_configuration(configuration, client), tools=[synthetic_probe], retries=0, model_settings={'max_tokens': 512})
            agent.instrument = False
            result = await agent.run('Read the synthetic number', usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1, total_tokens_limit=3000))
            assert result.output == '7' and calls == ['synthetic'] and len(requests) == 2
            assert result.usage.input_tokens == 40 and result.usage.output_tokens == 10
    assert client.is_closed() and http.is_closed
