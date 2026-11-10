"""Dispatch preferences reach mature SDK wire settings; unknown models fail closed."""
import json
import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from class_os.infrastructure.reasoning import reasoning_settings
from class_os.application.agent import AgentRejected


def test_unknown_models_and_unrecognized_effort_do_not_pretend_support():
    model = FunctionModel(lambda messages, info: None)
    assert reasoning_settings(model, None) == {}
    for effort in ['low', 'unlimited', '', False]:
        with pytest.raises(AgentRejected): reasoning_settings(model, effort)


@pytest.mark.parametrize('effort', ['low', 'medium', 'high'])
async def test_openai_effort_is_in_sdk_request(effort):
    calls = []
    def reply(request):
        body = json.loads(request.content); calls.append(body)
        assert body['reasoning_effort'] == effort
        return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 1, 'model': 'gpt-5-mini',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'OK'}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply), trust_env=False) as http:
        async with AsyncOpenAI(api_key='synthetic-only', base_url='https://provider.example.invalid/v1', max_retries=0, http_client=http) as client:
            model = OpenAIChatModel('gpt-5-mini', provider=OpenAIProvider(openai_client=client))
            assert (await Agent(model, model_settings=reasoning_settings(model, effort)).run('Synthetic')).output == 'OK'
    assert len(calls) == 1
