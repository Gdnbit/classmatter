"""Actual SDK/OpenAI wire settings; transport is offline, not a provider Eval."""
import json
from types import SimpleNamespace
import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from class_os.infrastructure.agent import WorkspaceStepPolicy
from class_os.infrastructure.workspace_actions import WorkspaceActionCapture


@pytest.mark.parametrize('mode', ['continuation', 'ordinary', 'repair'])
async def test_sdk_encodes_bounded_per_step_tool_choice_without_a_custom_loop(mode):
    capture = WorkspaceActionCapture(('synthetic',))
    policy = WorkspaceStepPolicy(capture, mode == 'continuation')
    if mode == 'repair':
        policy.repair_step = 1
    requests, calls = [], []
    def response(request):
        body = json.loads(request.content);requests.append(body)
        index = len(requests)
        if mode == 'ordinary':
            assert body['tool_choice'] == 'auto'
            message = {'role': 'assistant', 'content': '普通聊天。'}
        elif index == 1:
            assert body['tool_choice'] == ({'type': 'function', 'function': {'name': 'read_task_progress'}} if mode == 'continuation' else 'required')
            name = 'read_task_progress' if mode == 'continuation' else 'prepare_example'
            message = {'role': 'assistant', 'tool_calls': [{'id': str(index), 'type': 'function', 'function': {'name': name, 'arguments': '{}'}}]}
        elif mode == 'continuation' and index == 2:
            assert body['tool_choice'] == 'auto'
            message = {'role': 'assistant', 'tool_calls': [{'id': str(index), 'type': 'function', 'function': {'name': 'prepare_example', 'arguments': '{}'}}]}
        else:
            assert body['tool_choice'] == 'none'
            message = {'role': 'assistant', 'content': '请核对候选。'}
        return httpx.Response(200, json={'id': str(index), 'object': 'chat.completion', 'created': 1, 'model': 'synthetic',
            'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if 'tool_calls' in message else 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}})
    async def read_task_progress() -> dict:
        calls.append('read');return {'actions': []}
    async def prepare_example() -> dict:
        calls.append('prepare');capture.proposed = {'synthetic_candidate': True};return {'saved': False}
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        model = OpenAIChatModel('synthetic', provider=OpenAIProvider(api_key='synthetic-only', base_url='https://fixture.invalid/v1', http_client=client))
        agent = Agent(model, tools=[read_task_progress, prepare_example], capabilities=[policy], retries=0)
        agent.instrument = False
        result = await agent.run('synthetic acceptance only')
    assert result.output == ('普通聊天。' if mode == 'ordinary' else '请核对候选。')
    assert calls == ([] if mode == 'ordinary' else ['read', 'prepare'] if mode == 'continuation' else ['prepare'])
    assert len(requests) == (1 if mode == 'ordinary' else 3 if mode == 'continuation' else 2)
