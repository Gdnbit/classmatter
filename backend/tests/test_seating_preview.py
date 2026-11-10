"""Reproduce the screenshot: view seating, then confirm Chinese dimensions."""
from uuid import uuid4
from pathlib import Path
import os
import socket
import subprocess
import threading
import time
import httpx
import pytest
import uvicorn
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.infrastructure.seating_input import explicit_layout_dimensions, unbacked_seating_promise
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity

PROMISE = '已为您准备好一个三行五列的座位布局。请确认是否需要应用此布局？'


@pytest.mark.parametrize('text,expected', [('三行五列', (3, 5)), ('是，三行五列', (3, 5)), ('3排，每排5座', (3, 5)),
    ('两排十二座', (2, 12)), ('20行20列', (20, 20)), ('2×3座位', (2, 3)), ('5 rows and 3 columns', (5, 3)),
    ('3.5行5列', None), ('-3行5列', None), ('三十行五列', None), ('0行5列', None), ('成绩3分和5分', None),
    ('三行五列或五行三列', None), ('建立2排3座，把合成学生0放1排1座、合成学生1放1排2座，然后交换两人的座位。', (2, 3)),
    ('第3排5座', None)])
def test_explicit_dimensions_are_paired_bounded_and_not_scores(text, expected):
    assert explicit_layout_dimensions((text,)) == expected


def test_false_ready_guard_does_not_route_quote_or_ordinary_chat():
    assert unbacked_seating_promise(PROMISE, '是，三行五列')
    assert not unbacked_seating_promise(PROMISE, '仅讨论三行五列，不执行操作。')
    assert not unbacked_seating_promise(PROMISE, '不要创建三行五列座位。')
    assert not unbacked_seating_promise(PROMISE, '翻译：已准备三行五列座位，请确认。')
    assert not unbacked_seating_promise(PROMISE, '你好')
    assert not unbacked_seating_promise('请告诉我需要几行几列。', '三行五列')
    assert unbacked_seating_promise(PROMISE, '生成预览', ('看一下学生的座位', '是，三行五列'))
    assert not unbacked_seating_promise(PROMISE, '你好', ('看一下学生的座位', '是，三行五列'))


@pytest.mark.db
@pytest.mark.parametrize('case', ['repair', 'exhausted', 'direct', 'wrong-dimensions'])
async def test_followup_creates_real_candidate_or_fails_without_false_success(classroom_work, case):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    attempts, repairs = [], []
    def factory(request):
        def respond(messages, info):
            if request.text == '看一下学生的座位':
                return ModelResponse(parts=[TextPart('当前没有座位布局，需要几行几列？')])
            attempts.append(True)
            retry = any(isinstance(part, RetryPromptPart) for part in messages[-1].parts)
            if retry: repairs.append(True)
            if case == 'direct' or retry and case == 'repair':
                return ModelResponse(parts=[ToolCallPart('prepare_seat_layout', {'rows': 3, 'columns': 5})])
            if case == 'wrong-dimensions':
                if len(attempts) == 1:
                    return ModelResponse(parts=[ToolCallPart('prepare_seat_layout', {'rows': 5, 'columns': 3})])
                return ModelResponse(parts=[ToolCallPart('prepare_seat_layout', {'rows': 3, 'columns': 5})])
            return ModelResponse(parts=[TextPart(PROMISE)])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory)
    app = create_workspace_chat_app(Settings(), worker=business, query=query, sdk=sdk)
    headers = {'origin': 'http://127.0.0.1:8000', 'x-class-os-csrf': auth[2]}
    cookies = dict(zip(('class_os_session', 'class_os_client', 'class_os_csrf'), auth[:3]))
    prefix = f'/api/workspaces/{auth[3]}/workspace-chat/threads/{uuid4()}'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:8000', cookies=cookies) as client:
        for text in ['看一下学生的座位', '是，三行五列']:
            request = uuid4()
            assert (await client.post(prefix+'/turns', headers=headers, json={'request_id': str(request), 'text': text})).status_code == 200
            wire = await client.post(prefix+f'/turns/{request}/events', headers=headers, json={})
        row = (await client.get(prefix)).json()['turns'][-1]
        assert row['action_receipt'] is None and query.classroom_read(auth, c, t, seating=True) is None
        if case == 'exhausted':
            assert row['state'] == 'failed' and row['candidate'] is None and row['assistant_text'] is None
            assert 'message.delta' not in wire.text and len(repairs) == 1 and len(attempts) == 2
        else:
            assert row['state'] == 'completed', sdk.last_failure_type
            assert row['candidate']['command'] == 'seat.layout.create'
            assert (row['candidate']['rows'], row['candidate']['columns']) == (3, 5)
            assert len(attempts) == (1 if case == 'direct' else 2)
            value = await client.post(prefix+f'/turns/{request}/proposal', headers=headers, json={'candidate_hash': row['candidate_hash']})
            assert value.status_code == 200 and value.json()['payload']['rows'] == 3
            assert query.classroom_read(auth, c, t, seating=True) is None


@pytest.mark.db
def test_original_ui_followup_shows_grid_before_human_commit(classroom_work):
    from class_os.interfaces.http.web import mount_web
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    calls = []
    def factory(request):
        def respond(messages, info):
            calls.append(request.text)
            if request.text == '看一下学生的座位':
                if any(isinstance(part, ToolReturnPart) for part in messages[-1].parts):
                    return ModelResponse(parts=[TextPart('还没有座位表，需要几行几列？')])
                return ModelResponse(parts=[ToolCallPart('read_classroom_work', {'kind': 'seating'})])
            if any(isinstance(part, RetryPromptPart) for part in messages[-1].parts):
                return ModelResponse(parts=[ToolCallPart('prepare_seat_layout', {'rows': 3, 'columns': 5})])
            return ModelResponse(parts=[TextPart(PROMISE)])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = create_workspace_chat_app(Settings(port=port), worker=business, query=query, sdk=sdk)
    root = Path(__file__).resolve().parents[2]
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, proxy_headers=False, access_log=False, log_level='error', timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/seating-preview-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}', CLASS_OS_TEST_CLASS_ID=str(c), CLASS_OS_TEST_TERM_ID=str(t)),
            capture_output=True, text=True, encoding='utf-8', timeout=150, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (root / 'test-results/seat-preview-browser-details.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0, result.stdout + result.stderr
        layout = query.classroom_read(auth, c, t, seating=True)
        assert layout['rows'] == 3 and layout['columns'] == 5 and layout['version'] == 1
        assert len(calls) == 4 and sdk.active == 0
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
