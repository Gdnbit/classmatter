"""Original document flow, real PostgreSQL and HTTP, with one lost reply."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import pytest
import uvicorn
from fastapi.responses import JSONResponse
from sqlalchemy import text

from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from class_os.interfaces.http.workbench import create_workbench_app
from test_workbench_composition import workbench
from test_documents_gateway import documents, control, storage, roster, identity


@pytest.mark.db
@pytest.mark.parametrize('lost_reply', [False, True])
def test_original_document_editor_persistence_history_cas_archive_and_receipt_recovery(workbench, lost_reply):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = create_workbench_app(Settings(port=port), worker=workbench[0], query=workbench[1],
        sdk=PydanticAgentRuntime(workbench[1]))
    faults = []
    @app.middleware('http')
    async def lose_first_committed_reply(request, call_next):
        response = await call_next(request)
        if (lost_reply and not faults and request.method == 'POST'
                and request.url.path.endswith('/document-commands/commit') and response.status_code == 200):
            faults.append(True)
            return JSONResponse({'error': 'synthetic committed reply unavailable'}, status_code=503)
        return response
    root = Path(__file__).resolve().parents[2]
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
        proxy_headers=False, access_log=False, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        scope = workbench[5][5]
        result = subprocess.run(['node', 'tests/documents-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}',
                CLASS_OS_TEST_CLASS=str(scope['class']), CLASS_OS_TEST_TERM=str(scope['term']),
                CLASS_OS_TEST_LOST_REPLY='1' if lost_reply else '0'),
            capture_output=True, text=True, encoding='utf-8', timeout=160,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr
        assert faults == ([True] if lost_reply else [])
        with workbench[3].transaction(read_only=True) as connection:
            for table, count in (('student', 1), ('working_document', 1), ('working_document_revision', 5),
                                 ('export_job', 0), ('conversation_run', 0)):
                assert connection.execute(text(f'SELECT count(*) FROM class_os.{table}')).scalar_one() == count
            assert connection.execute(text('SELECT version,status FROM class_os.working_document')).one() == (5, 'draft')
    finally:
        server.should_exit = True; thread.join(timeout=8)
        assert not thread.is_alive()
