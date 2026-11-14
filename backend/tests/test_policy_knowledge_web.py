"""Original chat UI, actual SDK/tools/QG/HTTP/PG; deterministic model only."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import pytest
import uvicorn
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import text

from class_os.application.workbench import WorkbenchBusinessGateway
from class_os.infrastructure.agent import PydanticAgentRuntime
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.web import mount_web
from test_chat_note_recall import notes, workspace_chat, roster, identity


@pytest.mark.db
def test_original_chat_retrieval_evidence_gaps_and_refresh(notes):
    _, _, work, auth, owner, _, _, _, _ = notes
    with owner.transaction(read_only=True) as connection:
        initial_receipts = connection.execute(text('SELECT receipt_id FROM class_os.command_receipt ORDER BY receipt_id')).all()
    calls = []
    def factory(request):
        def respond(messages, info):
            returned = [part for part in messages[-1].parts if isinstance(part, ToolReturnPart)]
            if not returned:
                calls.append(request.text)
                return ModelResponse(parts=[ToolCallPart('search_policy_knowledge', {})])
            return ModelResponse(parts=[TextPart('已收录文件中的相关条款如下；学校具体安排仍需确认。')])
        return FunctionModel(respond)
    sdk = PydanticAgentRuntime(work, model_factory=factory, timeout=30)
    commands = WorkbenchBusinessGateway(work.identity, work.store, clock=work.clock)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[2]
    app = create_workspace_chat_app(Settings(port=port), worker=commands, query=work, sdk=sdk)
    mount_web(app, root / 'apps/web/dist')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, proxy_headers=False,
        access_log=False, log_level='error', timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(.05)
        result = subprocess.run(['node', 'tests/policy-knowledge-browser.mjs'], cwd=root / 'apps/web',
            env=dict(os.environ, CLASS_OS_TEST_URL=f'http://127.0.0.1:{port}'),
            capture_output=True, text=True, encoding='utf-8', timeout=130,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        (root / 'test-results/policy-knowledge-browser.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0, result.stdout + result.stderr
        assert len(calls) == 3 and sdk.active == 0
        with owner.transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT count(*) FROM class_os.school_class')).scalar_one() == 0
            assert connection.execute(text('SELECT receipt_id FROM class_os.command_receipt ORDER BY receipt_id')).all() == initial_receipts
            assert connection.execute(text("SELECT count(*) FROM class_os.workspace_chat_turn WHERE state='completed'")).scalar_one() == 3
    finally:
        server.should_exit = True; thread.join(timeout=10)
        assert not thread.is_alive()
