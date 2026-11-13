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


@pytest.mark.parametrize('mode', ['continuation', 'legacy-continuation', 'ordinary', 'repair', 'guarded-repair'])
async def test_sdk_encodes_bounded_per_step_tool_choice_without_a_custom_loop(mode):
    continuing = mode in ('continuation', 'legacy-continuation')
    capture = WorkspaceActionCapture(('synthetic',), classroom_enabled=mode != 'legacy-continuation')
    policy = WorkspaceStepPolicy(capture, continuing)
    reads_first = continuing or mode == 'guarded-repair'
    if mode == 'repair':
        policy.repair_step = 1
    if mode == 'guarded-repair':
        capture.repair_requires_progress = True
    requests, calls = [], []
    def response(request):
        body = json.loads(request.content);requests.append(body)
        index = len(requests)
        assert [tool['function']['name'] for tool in body['tools']] == (['read_task_progress'] if mode in ('continuation', 'guarded-repair') and index == 1 else ['read_task_progress', 'prepare_example'])
        if mode == 'ordinary':
            assert body['tool_choice'] == 'auto'
            message = {'role': 'assistant', 'content': '普通聊天。'}
        elif index == 1:
            assert body['tool_choice'] == ({'type': 'function', 'function': {'name': 'read_task_progress'}} if mode == 'legacy-continuation' else 'required')
            name = 'read_task_progress' if reads_first else 'prepare_example'
            message = {'role': 'assistant', 'tool_calls': [{'id': str(index), 'type': 'function', 'function': {'name': name, 'arguments': '{}'}}]}
        elif reads_first and index == 2:
            assert body['tool_choice'] == 'auto'
            message = {'role': 'assistant', 'tool_calls': [{'id': str(index), 'type': 'function', 'function': {'name': 'prepare_example', 'arguments': '{}'}}]}
        else:
            assert body['tool_choice'] == 'none'
            message = {'role': 'assistant', 'content': '请核对候选。'}
        return httpx.Response(200, json={'id': str(index), 'object': 'chat.completion', 'created': 1, 'model': 'synthetic',
            'choices': [{'index': 0, 'message': message, 'finish_reason': 'tool_calls' if 'tool_calls' in message else 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}})
    async def read_task_progress() -> dict:
        calls.append('read');capture.completed_tools.append('read_task_progress');capture.repair_requires_progress = False;return {'actions': []}
    async def prepare_example() -> dict:
        calls.append('prepare');capture.proposed = {'synthetic_candidate': True};return {'saved': False}
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        model = OpenAIChatModel('synthetic', provider=OpenAIProvider(api_key='synthetic-only', base_url='https://fixture.invalid/v1', http_client=client))
        agent = Agent(model, tools=[read_task_progress, prepare_example], capabilities=[policy], retries=0)
        agent.instrument = False
        result = await agent.run('synthetic acceptance only')
    assert result.output == ('普通聊天。' if mode == 'ordinary' else '请核对候选。')
    assert calls == ([] if mode == 'ordinary' else ['read', 'prepare'] if reads_first else ['prepare'])
    assert len(requests) == (1 if mode == 'ordinary' else 3 if reads_first else 2)


@pytest.mark.parametrize('repair', [False, True])
async def test_sdk_rejects_a_hidden_operation_before_progress_instead_of_executing_it(repair):
    from pydantic_ai.exceptions import UnexpectedModelBehavior
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    capture = WorkspaceActionCapture(('synthetic',), classroom_enabled=True)
    capture.repair_requires_progress = repair
    policy = WorkspaceStepPolicy(capture, not repair); calls = []
    async def read_task_progress() -> dict:
        calls.append('read');return {'actions': []}
    async def prepare_example() -> dict:
        calls.append('prepare');return {'saved': False}
    def ignore_schema(messages, info):
        assert [tool.name for tool in info.function_tools] == ['read_task_progress']
        return ModelResponse(parts=[ToolCallPart('prepare_example', {})])
    agent = Agent(FunctionModel(ignore_schema), tools=[read_task_progress, prepare_example], capabilities=[policy], retries=0)
    agent.instrument = False
    with pytest.raises(UnexpectedModelBehavior): await agent.run('synthetic acceptance only')
    assert calls == [] and capture.proposed is None


async def test_native_google_repair_advertises_only_progress_then_restores_tools(monkeypatch):
    from pydantic import SecretStr
    from class_os.infrastructure import model_provider
    from test_google_provider import CONFIG, KEY, SIGNATURE, packet, intercept
    capture = WorkspaceActionCapture(('synthetic',), classroom_enabled=True, repair_requires_progress=True)
    policy = WorkspaceStepPolicy(capture, False)
    requests, calls = [], []
    def reply(request):
        body = json.loads(request.content); requests.append(body)
        names = [tool['name'] for bundle in body.get('tools', []) for tool in bundle['functionDeclarations']]
        if len(requests) == 1:
            assert names == ['read_task_progress']
            settings = body['toolConfig']['functionCallingConfig']
            assert settings['mode'] == 'ANY'
            assert settings.get('allowedFunctionNames', ['read_task_progress']) == ['read_task_progress']
            parts = [{'functionCall': {'name': 'read_task_progress', 'args': {}}, 'thoughtSignature': SIGNATURE}]
        elif len(requests) == 2:
            assert names == ['read_task_progress', 'prepare_example']
            parts = [{'functionCall': {'name': 'prepare_example', 'args': {}}, 'thoughtSignature': SIGNATURE}]
        else:
            assert body['toolConfig']['functionCallingConfig']['mode'] == 'NONE'
            parts = [{'text': '请核对候选。'}]
        return httpx.Response(200, json=packet(parts))
    intercept(monkeypatch, reply)
    async def read_task_progress() -> dict:
        calls.append('read'); capture.repair_requires_progress = False
        return {'actions': []}
    async def prepare_example() -> dict:
        calls.append('prepare'); capture.proposed = {'synthetic_candidate': True}
        return {'saved': False}
    async with model_provider.configured_client(CONFIG, SecretStr(KEY)) as session:
        model = model_provider.model_for_configuration(CONFIG, session)
        agent = Agent(model, tools=[read_task_progress, prepare_example], capabilities=[policy], retries=0)
        agent.instrument = False
        result = await agent.run('Synthetic repair acceptance only')
    assert result.output == '请核对候选。' and calls == ['read', 'prepare'] and len(requests) == 3
