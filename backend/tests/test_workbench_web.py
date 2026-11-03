"""Original UI against actual D2 QG/ISB/BCG/socket/PG, not intercepted data."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import pytest
import uvicorn
from sqlalchemy import text

from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from class_os.interfaces.http.workbench import create_workbench_app
from test_workbench_composition import workbench
from test_documents_gateway import documents, control, storage, roster, identity, create, saved


@pytest.mark.db
def test_original_workbench_discovers_d2_and_reads_documents_audit_without_partial_exit(workbench):
    command = create(workbench)
    saved(workbench, command)
    workbench[1].document(*workbench[5][6], command.class_id, command.term_id, command.document_id)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = create_workbench_app(Settings(port=port), worker=workbench[0], query=workbench[1],
        sdk=PydanticAgentRuntime(workbench[1]))
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
        result = subprocess.run(['node', 'tests/workbench-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}'),
            capture_output=True, text=True, encoding='utf-8', timeout=80,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr
        with workbench[3].transaction(read_only=True) as connection:
            for table, count in (('student', 1), ('working_document', 1),
                                 ('working_document_revision', 1), ('export_job', 0), ('conversation_run', 0)):
                assert connection.execute(text(f'SELECT count(*) FROM class_os.{table}')).scalar_one() == count
    finally:
        server.should_exit = True; thread.join(timeout=8)
        assert not thread.is_alive()
