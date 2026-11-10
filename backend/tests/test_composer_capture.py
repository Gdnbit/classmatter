"""Input capture uses editable text, never a new business write path."""
import asyncio
import base64
from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile
import httpx
import pytest
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4
import uvicorn
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from class_os.infrastructure.composer_capture import CaptureRejected, decode_capture, document_text, capture_text, MAX_FILE
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.application.workspace_chat import WorkspaceChatQueryGateway
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


def encoded(value):
    return base64.b64encode(value).decode()


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'utf-16', 'gb18030'])
def test_windows_text_encodings_and_no_silent_truncation(encoding):
    value = '本周班级小结\n已完成三项工作'
    assert document_text('.txt', value.encode(encoding), 100) == value
    with pytest.raises(CaptureRejected, match='capture_too_long'):
        document_text('.txt', value.encode(encoding), 2)


def test_boundaries_and_xml_are_rejected_before_parsing():
    for name, value in [('bad.exe', b'x'), ('../a.txt', b'x'), ('a.txt', b'x' * (MAX_FILE + 1))]:
        with pytest.raises(CaptureRejected):
            decode_capture(name, encoded(value))
    with pytest.raises(CaptureRejected):
        decode_capture('a.txt', 'not base64')
    stream = BytesIO()
    with ZipFile(stream, 'w') as archive:
        archive.writestr('word/document.xml', '<!DOCTYPE x [<!ENTITY x SYSTEM "file:///missing">]><x/>')
    with pytest.raises(CaptureRejected, match='invalid_file'):
        document_text('.docx', stream.getvalue(), 2000)


@pytest.mark.parametrize('suffix', ['.docx', '.xlsx', '.pptx'])
def test_mature_office_readers_extract_editable_text(suffix):
    output = BytesIO()
    if suffix == '.docx':
        from docx import Document
        document = Document(); document.add_paragraph('本周小结'); document.save(output)
    elif suffix == '.xlsx':
        from openpyxl import Workbook
        document = Workbook(); document.active.append(['本周小结', 3]); document.save(output)
    else:
        from pptx import Presentation
        document = Presentation(); document.slides.add_slide(document.slide_layouts[0]).shapes.title.text = '本周小结'; document.save(output)
    assert '本周小结' in document_text(suffix, output.getvalue(), 2000)
    with pytest.raises(CaptureRejected, match='capture_too_long'):
        document_text(suffix, output.getvalue(), 2)


async def test_media_uses_current_sdk_with_no_tools_and_releases_cancelled_capacity():
    audits, requests = [], []
    query = SimpleNamespace(agent_workspace_context=lambda *args: {}, agent_audit=lambda *args, **kwargs: audits.append(args[2]))
    runtime = SimpleNamespace(active=0)
    async def status(auth):
        return {'mode': 'configured-api'}
    @asynccontextmanager
    async def context(auth, request):
        def answer(messages, info):
            requests.append(messages)
            assert not info.function_tools
            return ModelResponse(parts=[TextPart('合成图片文字')])
        yield FunctionModel(answer)
    controller = SimpleNamespace(status=status, runtime=runtime, context=context)
    assert await capture_text(query, controller, (), 'a.png', encoded(b'\x89PNG\r\n\x1a\nsynthetic'), 100) == '合成图片文字'
    assert audits == ['started', 'completed'] and len(requests) == 1 and runtime.active == 0
    entered = asyncio.Event()
    @asynccontextmanager
    async def waiting(auth, request):
        entered.set(); await asyncio.sleep(30); yield None
    controller.context = waiting
    job = asyncio.create_task(capture_text(query, controller, (), 'a.png', encoded(b'\x89PNG\r\n\x1a\nsynthetic'), 100))
    await entered.wait(); job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job
    assert runtime.active == 0 and audits[-1] == 'cancelled'


@pytest.mark.db
async def test_capture_original_d4_http_requires_identity_but_not_class(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    app = create_workspace_chat_app(Settings(), worker=business, query=query, sdk=PydanticAgentRuntime(query))
    path = f'/api/workspaces/{auth[3]}/composer/capture'
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    cookies = dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))
    body = {'name': '小结.txt', 'data': encoded('本周小结'.encode()), 'capacity': 2000}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:8000') as client:
        assert (await client.post(path, json=body, headers=headers)).status_code in (401, 403)
        client.cookies.update(cookies)
        response = await client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == {'schema_version': 'classmatter.composer-capture.v1', 'text': '本周小结'}
        assert (await client.post(path, json=body, headers={'origin': headers['origin']})).status_code == 403
        assert (await client.post(path, json={**body, 'capacity': 1}, headers=headers)).json()['error'] == 'capture_too_long'
        assert (await client.post(path, json={**body, 'ignored': True}, headers=headers)).status_code == 400
        assert (await client.post(path, content='{"name":"a.txt","name":"b.txt"}', headers={**headers, 'content-type': 'application/json'})).status_code == 400
        events = f'/api/workspaces/{auth[3]}/workspace-chat/threads/{uuid4()}/turns/{uuid4()}/events'
        for options in [('x-classmatter-reasoning', 'unlimited')], [('x-classmatter-reasoning', 'low'), ('x-classmatter-reasoning', 'high')]:
            assert (await client.post(events, json={}, headers=list(headers.items()) + options)).status_code == 400
    assert WorkspaceChatQueryGateway(query.identity, query.store, clock=query.clock).listing(auth)['data'] == []


@pytest.mark.db
def test_composer_original_ui_import_dictation_and_draft_isolation(classroom_work):
    """Real HTTP/PG/UI with an explicitly synthetic media provider, no external calls."""
    from class_os.interfaces.http.web import mount_web
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    def factory(request):
        return FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart('合成回复已完成')]))
    sdk = PydanticAgentRuntime(query, model_factory=factory)
    async def status(credentials):
        query.agent_workspace_context(*credentials)
        return {'schema_version': 'class-os.model-status.v1', 'storage_available': True, 'version': 1,
                'candidate_id': str(uuid4()), 'configuration': {'protocol': 'chat-completions', 'model': 'gemini-3.1-flash-lite',
                'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/'}, 'key_configured': True,
                'network_permitted': True, 'test_passed': True, 'mode': 'configured-api'}
    @asynccontextmanager
    async def context(credentials, request):
        async def answer(messages, info):
            if request.text == 'User-selected input capture':
                assert not info.function_tools
            await asyncio.sleep(.6)
            return ModelResponse(parts=[TextPart('合成识别文字' if request.text == 'User-selected input capture' else '合成回复已完成')])
        yield FunctionModel(answer)
    from class_os.infrastructure.model_control import ModelController
    from class_os.infrastructure.model_secrets import ModelSecrets
    from test_model_secrets import fixture_codec
    vault = ModelSecrets(fixture_codec, clock=lambda: clock[0]); store.model_secrets = vault
    controller = ModelController(query, vault, sdk, clock=lambda: clock[0])
    controller.status, controller.context = status, context
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = create_workspace_chat_app(Settings(port=port), worker=business, query=query, sdk=sdk, model_controller=controller)
    root = Path(__file__).resolve().parents[2]
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, proxy_headers=False, access_log=False, log_level='error', timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/composer-input-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}'), capture_output=True, text=True, encoding='utf-8',
            timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (root / 'test-results/composer-browser-details.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0, result.stdout + result.stderr
        assert sdk.active == 0
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
