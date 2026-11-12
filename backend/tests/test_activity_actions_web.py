"""Original UI + actual SDK/HTTP/PG; FunctionModel is explicitly synthetic."""
from pathlib import Path
import os
import socket
import subprocess
import threading
import time

import pytest
import uvicorn
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


@pytest.mark.db
def test_original_chat_record_followup_wait_end_summary_and_retry(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    fact, title = '合成学生0交来展示作品', '合成作品核对'
    failed, observed = [], []
    def factory(request):
        sources = {}
        def respond(messages, info):
            returned = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
            if not returned:
                if '班长交齐' in request.text and not failed:
                    failed.append(request.text)
                    raise ModelHTTPError(503, 'synthetic', body={'error': {'status': 'UNAVAILABLE'}})
                return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
            last = returned[-1]
            if '生成合成工作小结' in request.text:
                if last.tool_name == 'read_task_progress':
                    return ModelResponse(parts=[ToolCallPart('read_class_records', {'student_name': '合成学生0'})])
                if last.tool_name == 'read_class_records':
                    sources['record'] = last.content['items'][0]
                    return ModelResponse(parts=[ToolCallPart('read_class_work', {'kind': 'tasks'})])
                if last.tool_name == 'read_class_work':
                    record, task = sources['record'], last.content['items'][0]
                    observed.append((record, task))
                    body = (f"事实：{record['student']}，{record['fact_text']}。\n"
                        f"已完成：{task['title']}，{task['evidence']}。\n"
                        f"来源：学生普通记录v{record['version']}（{record['occurred_at']}）；任务v{task['version']}。")
                    return ModelResponse(parts=[ToolCallPart('prepare_document', {'action': 'create', 'title': '合成工作小结', 'body': body})])
            if '先等待' in request.text:
                return ModelResponse(parts=[ToolCallPart('prepare_task', {'action': 'edit', 'title': title, 'status': 'waiting', 'evidence': '班长正在收集'})])
            if '结束' in request.text:
                return ModelResponse(parts=[ToolCallPart('prepare_task', {'action': 'complete', 'title': title,
                    'evidence': '班长交齐，我已核对' if '班长交齐' in request.text else ''})])
            committed = {row['command'] for row in last.content['actions'] if row['status'] == 'committed'}
            if 'record.create' not in committed:
                return ModelResponse(parts=[ToolCallPart('prepare_record', {'student_name': '合成学生0', 'fact_text': fact, 'occurred_now': True})])
            if 'task.create' not in committed:
                return ModelResponse(parts=[ToolCallPart('prepare_task', {'action': 'create', 'title': title, 'student_name': '合成学生0', 'source_fact': fact})])
            return ModelResponse(parts=[TextPart('记录和跟进已保存。')])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory, timeout=45)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = create_workspace_chat_app(Settings(port=port), worker=business, query=query, sdk=sdk)
    @app.get('/__fixture__/activity')
    def projection():
        value = query.projection(*auth, c, t)
        return {'records': len(value['records']), 'tasks': len(value['tasks']),
            'status': value['tasks'][0]['status'] if value['tasks'] else None,
            'version': value['tasks'][0]['version'] if value['tasks'] else None,
            'documents': len(query.documents(*auth, c, t))}
    root = Path(__file__).resolve().parents[2]
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, proxy_headers=False, access_log=False, log_level='error', timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/activity-actions-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}'), capture_output=True,
            text=True, encoding='utf-8', timeout=150, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr + str(sdk.last_failure_type)
        assert len(failed) == len(observed) == 1 and sdk.active == 0
        assert observed[0][1]['status'] == 'done' and observed[0][1]['evidence'] == '班长交齐，我已核对'
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT count(*) FROM class_os.record_revision')).scalar_one() == 1
            assert connection.execute(text('SELECT count(*) FROM class_os.manual_task')).scalar_one() == 1
            assert connection.execute(text('SELECT version FROM class_os.manual_task')).scalar_one() == 3
            body = connection.execute(text('SELECT body FROM class_os.working_document_revision')).scalar_one()
            assert fact in body and '班长交齐，我已核对' in body and '任务v3' in body
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
