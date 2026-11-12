"""Original document page and actual downloads, no provider or mock business data."""
from dataclasses import replace
from pathlib import Path
import os
import socket
import subprocess
import threading
import time
from uuid import uuid4

import pytest
import uvicorn
from docx import Document
from pptx import Presentation
from sqlalchemy import text

from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from class_os.interfaces.http.workbench import create_workbench_app
from test_workbench_composition import workbench
from test_documents_gateway import documents, control, storage, roster, identity, create, saved


@pytest.mark.db
def test_original_document_office_download_dirty_errors_and_navigation(workbench, tmp_path):
    command = replace(create(workbench), body='# 课堂目标\n认识分数。\n# 课堂活动\n学生分组讨论。')
    saved(workbench, command)
    destination = Path(os.environ.get('CLASSMATTER_TEST_DOWNLOAD_ROOT', str(tmp_path))) / ('office-' + uuid4().hex)
    destination.mkdir(parents=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = create_workbench_app(Settings(port=port), worker=workbench[0], query=workbench[1], sdk=PydanticAgentRuntime(workbench[1]))
    root = Path(__file__).resolve().parents[2]
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, proxy_headers=False, access_log=False, log_level='error', timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/office-artifacts-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}', CLASSMATTER_TEST_DOWNLOAD_ROOT=str(destination)),
            capture_output=True, text=True, encoding='utf-8', timeout=100, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr
        assert '认识分数。' in [p.text for p in Document(str(destination / 'lesson.docx')).paragraphs]
        assert Presentation(str(destination / 'lesson.pptx')).slides[1].shapes[0].text == '课堂目标'
        with workbench[3].transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT count(*) FROM class_os.working_document_revision')).scalar_one() == 1
            assert connection.execute(text('SELECT count(*) FROM class_os.export_job')).scalar_one() == 0
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
