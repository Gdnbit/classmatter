"""Opt-in real free provider, synthetic PG fixture; never calls a model in CI.

Set CLASSMATTER_POLICY_LIVE=approved-free-only plus explicit existing source
and non-system artifact roots. No key argument, paid profile or source reset.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.local_runtime import LocalRuntime
from class_os.infrastructure.local_model_activation import LocalModelActivation
from class_os.infrastructure.model_control import ModelController
from class_os.infrastructure.model_provider import configured_client, model_for_configuration
from class_os.infrastructure.native_setup import NativeSetup
from class_os.infrastructure.workspace_local_runtime import open_services
from class_os.infrastructure.workspace_chat_runtime import WorkspaceChatRuntime
from test_chat_note_recall import notes, workspace_chat, roster, identity


@pytest.mark.db
@pytest.mark.skipif(os.environ.get('CLASSMATTER_POLICY_LIVE') != 'approved-free-only', reason='Explicit approved free-provider experiment only')
async def test_real_free_policy_tool_selection_and_persistence(notes):
    business, query, work, auth, _, _, _, _, _ = notes
    source_root = Path(os.environ['CLASSMATTER_POLICY_SOURCE_ROOT']).resolve()
    artifacts = Path(os.environ['CLASSMATTER_POLICY_ARTIFACT_ROOT']).resolve()
    if os.name != 'nt' or artifacts.drive.lower() == 'c:' or artifacts.is_relative_to(Path(__file__).resolve().parents[2]):
        pytest.fail('Owned Windows source and non-system, non-repository artifact root required')
    output = artifacts / uuid4().hex
    output.mkdir(parents=True, exist_ok=False)
    source = LocalRuntime(source_root, profile='classroom-work-d4')
    services, reports = None, []
    try:
        cookies = NativeSetup(source, development=True).handle({'operation': 'development_access'})['cookies']
        services = open_services(source, local_development=True)
        existing = (cookies['session'], cookies['client'], cookies['csrf'], services.restrictions.workspace_id)
        row = services.query.model_configuration(existing)
        activation = LocalModelActivation(source.root, existing[3]).read()
        assert row and activation
        assert (str(row['candidate_id']), row['version']) == (activation['candidate_id'], activation['version'])
        profile = ModelController.profile(row)
        assert profile.model == 'gemini-3.1-flash-lite'
        assert profile.base_url == 'https://generativelanguage.googleapis.com/v1beta/openai/'
        key = services.worker.store.model_secrets.open(existing[3], row['candidate_id'], row['version'], profile, bytes(row['sealed']))

        @asynccontextmanager
        async def context(credentials, request):
            async with configured_client(profile, key, proxy=activation['proxy']) as client:
                yield model_for_configuration(profile, client)

        diagnostics = []
        sdk = PydanticAgentRuntime(work, model_context=context, provider_label='managed-model', timeout=100, diagnostics=diagnostics.append)
        runtime = WorkspaceChatRuntime(business, query, sdk)
        for question, expected in (
            ('宁乡县初中进校园活动有什么教师减负依据？请引用原文，也说明有没有核实当前效力。', '[P1]'),
            ('宁乡某校办公室内部报销上限是多少？查现有资料，不要猜。', '没有找到'),
            ('宁乡小学把成绩排名发到家长群，有哪些已收录的规定可以核对？', '[P2]'),
        ):
            thread, passed = uuid4(), False
            for attempt in range(1, 4):
                request = uuid4()
                business.send(auth, thread, request, question)
                events = [e async for e in runtime.stream_queued(auth, thread, request)]
                stored = query.history(auth, thread)['turns'][-1]
                tools = [e.payload.get('tool') for e in events if e.type == 'tool.completed']
                passed = stored['state'] == 'completed' and expected in (stored['assistant_text'] or '') and 'search_policy_knowledge' in tools and stored['candidate'] is None
                reports.append({'question': question, 'attempt': attempt, 'state': stored['state'],
                    'tools': tools, 'passed': passed, 'answer': stored['assistant_text'], 'diagnostics': diagnostics[-1:]})
                (output / 'report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf-8')
                if passed or stored['state'] == 'completed':
                    break
                if attempt < 3:
                    await asyncio.sleep(15)  # explicit finite experiment retries, not product policy
            assert passed, 'Live scenario failed; original attempts retained in local report'
        assert sdk.active == 0
    finally:
        if services is not None:
            services.close()
