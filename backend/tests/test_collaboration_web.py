"""Two real HTTP servers and two original browser contexts over isolated PG."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from uuid import uuid4

import pytest
import uvicorn

from class_os.domain.documents import CreateDocument
from class_os.interfaces.http.settings import Settings
from class_os.interfaces.http.workspace_chat import create_workspace_chat_app
from class_os.interfaces.http.web import mount_web
from test_collaboration_runtime import two_classrooms,model
from test_personal_summary_runtime import assembly
from test_classroom_work_storage import classroom_work,workspace_chat,roster,identity


@pytest.mark.db
def test_original_two_teacher_interfaces_collect_share_preview_and_save(two_classrooms):
    root=Path(__file__).resolve().parents[2]
    a,b=two_classrooms
    b[6](CreateDocument(uuid4(),b[7],b[8],'本周教学进度','数学完成第三单元，周五已核对练习。','markdown'))
    servers=[];threads=[];addresses=[];failures=[]
    try:
        for fixture in two_classrooms:
            _,_,sdk,_,_,_=assembly(fixture)
            sdk.model_factory=model
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            app=create_workspace_chat_app(Settings(port=port),worker=fixture[0],query=fixture[1],sdk=sdk)
            app.state.personal_summary.interval=1
            old=app.exception_handlers[Exception]
            async def capture(request,error,original=old):
                failures.append(type(error).__name__+': '+str(error))
                return await original(request,error)
            app.add_exception_handler(Exception,capture)
            mount_web(app,root/'apps/web/dist')
            server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,proxy_headers=False,
                access_log=False,log_level='error',timeout_graceful_shutdown=5))
            thread=threading.Thread(target=server.run,daemon=True);thread.start()
            servers.append(server);threads.append(thread);addresses.append(f'http://127.0.0.1:{port}')
            deadline=time.monotonic()+10
            while not server.started:
                assert thread.is_alive() and time.monotonic()<deadline
                time.sleep(.05)
        result=subprocess.run(['node','tests/collaboration-browser.mjs'],cwd=root/'apps/web',
            env=dict(os.environ,CLASS_OS_TEST_URL_A=addresses[0],CLASS_OS_TEST_URL_B=addresses[1]),capture_output=True,
            text=True,encoding='utf-8',timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        (root/'test-results/collaboration-browser.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        assert result.returncode==0,(result.stderr[-7000:],failures)
        assert not failures,failures
        docs=a[1].documents(*a[2],a[7],a[8])
        assert len(docs)==1 and docs[0]['version']==1
        body=a[1].document(*a[2],a[7],a[8],docs[0]['document_id'])['body']
        assert '合成王老师提供：《本周教学进度》（第1版）' in body
        assert body.endswith('数学完成第三单元，周五已核对练习。')
    finally:
        for server in servers:server.should_exit=True
        for thread in threads:
            thread.join(timeout=12)
            assert not thread.is_alive()
