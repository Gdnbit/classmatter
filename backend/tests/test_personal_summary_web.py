"""Original UI, actual HTTP/SDK/QG/BCG/PG; no external provider or user data."""
from datetime import timedelta
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import pytest
import uvicorn

from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_personal_summary_runtime import assembly, materials, classroom_work, workspace_chat, roster, identity


@pytest.mark.db
def test_original_ui_proactive_summary_feedback_and_refresh(classroom_work):
    business, query, _, _, clock, _, _, c, t, _ = classroom_work
    materials(classroom_work)
    _, _, sdk, _, _, _ = assembly(classroom_work)
    original_factory = sdk.model_factory
    def factory(request):
        if request.text.startswith('以后用三条'):
            clock[0] += timedelta(minutes=2)  # Controlled fixture clock, not a production timer shortcut.
        return original_factory(request)
    sdk.model_factory = factory
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = create_workspace_chat_app(Settings(port=port), worker=business, query=query, sdk=sdk)
    failures = []
    original_handler = app.exception_handlers[Exception]
    async def capture_failure(request, error):
        failures.append(type(error).__name__ + ': ' + str(error))
        return await original_handler(request, error)
    app.add_exception_handler(Exception, capture_failure)
    app.state.personal_summary.interval = 1
    root = Path(__file__).resolve().parents[2]
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, proxy_headers=False,
        access_log=False, log_level='error', timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/personal-summary-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}'), capture_output=True,
            text=True, encoding='utf-8', timeout=150, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (root / 'test-results/personal-summary-browser.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0, (result.stderr[-6500:], failures, sdk.last_failure_type)
        # UI output is checked against actual stored business entities too.
        auth = classroom_work[2]
        documents = query.documents(*auth, c, t)
        assert len(documents) == 2
        summary = next(row for row in documents if row['title'] == '班级工作小结')
        assert summary['version'] == 2
        assert query.document(*auth, c, t, summary['document_id'])['body'].count('\n- ') == 2
    finally:
        server.should_exit = True; thread.join(timeout=12)
        assert not thread.is_alive()
