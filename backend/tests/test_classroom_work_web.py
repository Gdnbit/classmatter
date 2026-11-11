"""Original UI classroom pack integration, disposable PG and FunctionModel."""
from pathlib import Path
from collections import Counter
import os
import socket
import subprocess
import threading
import time
import pytest
import uvicorn
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from sqlalchemy import text
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from class_os.domain.classroom_work import RecordScore
from test_classroom_work_storage import classroom_work, workspace_chat, roster, identity


@pytest.mark.db
def test_original_chat_multistep_grades_seats_same_world_and_failures(classroom_work):
    business, query, auth, owner, clock, store, commit, c, t, students = classroom_work
    calls = []
    def factory(request):
        target = [None]
        def respond(messages, info):
            returned = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
            if not returned:
                calls.append(request.text)
                return ModelResponse(parts=[ToolCallPart('read_task_progress', {})])
            if returned[-1].tool_name == 'read_task_progress':
                counts = Counter(action['command'] for action in returned[-1].content['actions'] if action['status'] == 'committed')
                if not counts['exam.create']:
                    target[0] = 'prepare_exam', {'title': '合成浏览月考', 'subject': '数学', 'maximum_score': '100'}
                elif not counts['score.record']:
                    target[0] = 'prepare_score', {'exam_title': '合成浏览月考', 'subject': '数学', 'student_name': '合成学生0', 'status': 'scored', 'score': '80'}
                elif not counts['seat.layout.create']:
                    target[0] = 'prepare_seat_layout', {'rows': 2, 'columns': 3}
                elif counts['seat.assign'] < 2:
                    index = counts['seat.assign']
                    target[0] = 'prepare_seat_assignment', {'student_name': f'合成学生{index}', 'row': 1, 'column': index + 1}
                elif not counts['seat.swap']:
                    target[0] = 'prepare_seat_swap', {'first_student': '合成学生0', 'second_student': '合成学生1'}
                else:
                    return ModelResponse(parts=[TextPart('六步已完成，没有重复操作。')])
                return ModelResponse(parts=[ToolCallPart('read_classroom_work', {'kind': 'exams'})])
            if returned[-1].tool_name == 'read_classroom_work':
                return ModelResponse(parts=[ToolCallPart(*target[0])])
            return ModelResponse(parts=[TextPart('已准备下一步，请核对确认。')])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(query, model_factory=factory, timeout=45)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = create_workspace_chat_app(Settings(port=port), worker=business, query=query, sdk=sdk)
    @app.post('/__fixture__/concurrent-score')
    def change_score():
        exam = query.classroom_read(auth, c, t)['exams'][0]['exam_id']
        commit(RecordScore(exam, c, t, students[0], 2, 'scored', '86', '合成并发核对'))
        return {'changed': True}
    root = Path(__file__).resolve().parents[2]
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, proxy_headers=False, access_log=False, log_level='error', timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/classroom-work-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}'), capture_output=True, text=True, encoding='utf-8',
            timeout=200, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (root / 'test-results/classroom-browser-details.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            pytest.fail(f'Original classroom browser failed ({sdk.last_failure_type}); calls={len(calls)}\n{result.stdout}{result.stderr}')
        assert len(calls) == 7 and sdk.active == 0
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT count(*) FROM class_os.class_exam')).scalar_one() == 1
            assert connection.execute(text('SELECT count(*) FROM class_os.exam_result_revision')).scalar_one() == 3
            assert connection.execute(text('SELECT version FROM class_os.class_seating')).scalar_one() == 6
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
