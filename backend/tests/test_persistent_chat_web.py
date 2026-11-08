"""Original UI against real SDK/HTTP/PG, synthetic provider and data only."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import uvicorn
import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from sqlalchemy import text

from class_os.application.workbench import WorkbenchBusinessGateway, WorkbenchQueryGateway
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_workspace_chat_storage import workspace_chat, roster, identity
from class_os.infrastructure.model_control import ModelController
from class_os.infrastructure.model_secrets import ModelSecrets
from class_os.domain.model_configuration import ModelConfiguration, Protocol
from test_model_secrets import fixture_codec
from test_agent_api_protocol import protocol_reply


@pytest.mark.db
def test_original_ui_persistent_chat_actions_and_same_world_views(workspace_chat):
    _, _, credentials, owner, _, clock, store, boundary = workspace_chat
    commands = WorkbenchBusinessGateway(boundary, store, clock=lambda: clock[0])
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    calls = []
    mapping = {
        '建立合成七一班，合成第一学期，2026-09-01至2027-01-30': ('prepare_class_create', {'name': '合成七一班', 'term_name': '合成第一学期', 'start_date': '2026-09-01', 'end_date': '2027-01-30'}),
        '把班名改为合成七二班': ('prepare_class_edit', {'name': '合成七二班'}),
        '添加合成学生甲': ('prepare_student', {'action': 'create', 'name': '合成学生甲'}),
        '将合成学生甲改名为合成学生乙': ('prepare_student', {'action': 'rename', 'name': '合成学生甲', 'new_name': '合成学生乙'}),
        '建立任务合成收集回执': ('prepare_task', {'action': 'create', 'title': '合成收集回执'}),
        '把任务合成收集回执改为合成收集签字回执': ('prepare_task', {'action': 'edit', 'title': '合成收集回执', 'new_title': '合成收集签字回执'}),
        '生成文档合成班级小结': ('prepare_document', {'action': 'create', 'title': '合成班级小结', 'body': '合成小结正文，待核对。'}),
        '给合成班级小结追加合成补充段落': ('prepare_document', {'action': 'edit', 'edit_mode': 'append', 'title': '合成班级小结', 'body': '合成补充段落'}),
    }
    def factory(request):
        def respond(messages, info):
            if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
                return ModelResponse(parts=[TextPart('合成候选已准备；核对后在对话中确认，不会自动保存。')])
            calls.append(request.text)
            if request.text not in mapping:
                return ModelResponse(parts=[TextPart('合成普通聊天已回复，不需要班级。')])
            return ModelResponse(parts=[ToolCallPart(*mapping[request.text])])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    app = create_workspace_chat_app(Settings(port=port), worker=commands, query=query, sdk=sdk)
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, proxy_headers=False, access_log=False, log_level='error', timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/persistent-chat-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}'), capture_output=True,
            text=True, encoding='utf-8', timeout=240, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (root / 'test-results/ui-v3-browser-details.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0, result.stdout + result.stderr
        assert len(calls) == len(mapping) + 2
        assert sdk.active == 0
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT count(*) FROM class_os.workspace_chat_thread')).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM class_os.workspace_chat_turn WHERE state='completed'")).scalar_one() == len(mapping) + 2
            assert connection.execute(text('SELECT count(*) FROM class_os.school_class')).scalar_one() == 1
            assert connection.execute(text('SELECT count(*) FROM class_os.student')).scalar_one() == 1
            assert connection.execute(text('SELECT count(*) FROM class_os.manual_task')).scalar_one() == 1
            assert connection.execute(text('SELECT count(*) FROM class_os.working_document_revision')).scalar_one() == 2
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()


@pytest.mark.db
def test_original_composer_switches_model_without_losing_draft(workspace_chat):
    _, _, auth, owner, _, clock, store, boundary = workspace_chat
    worker = WorkbenchBusinessGateway(boundary, store, clock=lambda: clock[0])
    query = WorkbenchQueryGateway(boundary, store, clock=lambda: clock[0])
    vault = ModelSecrets(fixture_codec, clock=lambda: clock[0]); store.model_secrets = vault
    command = vault.stage(auth, ModelConfiguration(Protocol.CHAT, 'synthetic-original', 'https://provider.example.invalid/v1'), 'synthetic-ui-switch-canary', 0)
    proposal = worker.preview(*auth, command)
    worker.commit(*auth, proposal.proposal_id, uuid4(), worker.approve(*auth, proposal.proposal_id, proposal.payload_hash))
    calls = []
    @asynccontextmanager
    async def factory(profile, secret):
        def reply(request):
            body = json.loads(request.content); calls.append(body['model'])
            probe = any(tool['function']['name'] == 'class_os_probe' for tool in body.get('tools', []))
            packet = protocol_reply('chat-completions', body if probe else {**body, 'tools': []}, len(calls))
            packet['model'] = body['model']
            if not probe: packet['choices'][0]['message']['content'] = '合成模型切换后回复'
            return httpx.Response(200, json=packet)
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply), trust_env=False) as http:
            async with AsyncOpenAI(api_key=secret.get_secret_value(), base_url=profile.base_url, max_retries=0,
                organization='', project='', http_client=http) as client:
                yield client
    sdk = PydanticAgentRuntime(query)
    controller = ModelController(query, vault, sdk, allowed_bases=('https://provider.example.invalid/v1',), client_factory=factory, clock=lambda: clock[0])
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    app = create_workspace_chat_app(Settings(port=port), worker=worker, query=query, sdk=sdk, model_controller=controller)
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', access_log=False, timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/model-switch-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}'), capture_output=True, text=True,
            encoding='utf-8', timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr
        assert calls == ['synthetic-switched'] * 3
        assert query.model_configuration(auth)['model'] == 'synthetic-switched'
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT count(*) FROM class_os.workspace_chat_turn')).scalar_one() == 1
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
