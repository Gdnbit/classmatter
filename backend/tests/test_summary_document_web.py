"""Sourced summary -> original document -> explicit BCG save, real PG/HTTP/UI."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from uuid import uuid4

import pytest
import uvicorn
from sqlalchemy import text

from class_os.domain.activity import CreateRecord, CreateTask
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from class_os.interfaces.http.workbench import create_workbench_app
from test_workbench_composition import workbench
from test_documents_gateway import documents, control, storage, roster, identity


@pytest.mark.db
def test_original_summary_transfers_without_write_then_persists_only_as_document(workbench):
    ids, credentials, now = workbench[5][5], workbench[5][6], workbench[5][7][0]
    record = CreateRecord('record.create', uuid4(), ids['class'], ids['term'], ids['student'],
        'ordinary_fact', now, 'synthetic sourced document fact', 'synthetic observation is not a fact')
    task = CreateTask('task.create', uuid4(), ids['class'], ids['term'], 'synthetic sourced document task',
        None, ids['student'], record.record_id)
    for command in (record, task):
        proposal = workbench[0].preview(*credentials, command)
        workbench[0].commit(*credentials, proposal.proposal_id, uuid4())
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
        result = subprocess.run(['node', 'tests/summary-document-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}',
                CLASS_OS_TEST_CLASS=str(ids['class']), CLASS_OS_TEST_TERM=str(ids['term']),
                CLASS_OS_TEST_RECORD=str(record.record_id), CLASS_OS_TEST_TASK=str(task.task_id)),
            capture_output=True, text=True, encoding='utf-8', timeout=100,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr
        with workbench[3].transaction(read_only=True) as connection:
            for table, count in (('record_revision', 1), ('manual_task', 1), ('working_document', 1),
                                 ('working_document_revision', 1), ('conversation_run', 0), ('export_job', 0)):
                assert connection.execute(text(f'SELECT count(*) FROM class_os.{table}')).scalar_one() == count
            assert connection.execute(text('SELECT version FROM class_os.manual_task')).scalar_one() == 1
            body = connection.execute(text('SELECT body FROM class_os.working_document_revision')).scalar_one()
            assert f'[record:{record.record_id}@1]' in body and f'[task:{task.task_id}@1]' in body
    finally:
        server.should_exit = True; thread.join(timeout=8)
        assert not thread.is_alive()
