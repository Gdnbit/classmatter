"""Real Windows host download policy/Save path with an owned disposable fixture."""
import os
from pathlib import Path
import socket
import subprocess
from uuid import uuid4

import pytest
from docx import Document
from pptx import Presentation

from class_os.domain.documents import CreateDocument
from class_os.infrastructure.classroom_upgrade import upgrade_classroom
from class_os.infrastructure.workspace_upgrade import upgrade_workspace_chat
from class_os.infrastructure.workspace_local_runtime import open_services
from class_os.infrastructure.native_setup import NativeSetup
from test_workbench_upgrade import owned_upgrade


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows Electron/DPAPI runtime')
def test_original_desktop_office_files_save_and_reopen(owned_upgrade, tmp_path):
    runtime = upgrade_classroom(upgrade_workspace_chat(owned_upgrade.runtime))
    native = NativeSetup(runtime, development=True)
    try:
        cookies = native.handle({'operation': 'development_access'})['cookies']
    finally:
        native.close()
    auth = cookies['session'], cookies['client'], cookies['csrf'], owned_upgrade.workspace_id
    services = open_services(runtime, local_development=True)
    try:
        context = services.query.context(*auth)
        command = CreateDocument(uuid4(), context.class_id, context.term_id, '合成桌面教案', '# 课堂目标\n认识分数。', 'markdown')
        proposal = services.worker.preview(*auth, command)
        approval = services.worker.approve(*auth, proposal.proposal_id, proposal.payload_hash)
        services.worker.commit(*auth, proposal.proposal_id, uuid4(), approval)
    finally:
        services.close()
    destination = Path(os.environ.get('CLASSMATTER_TEST_DOWNLOAD_ROOT', str(tmp_path))) / ('native-office-' + uuid4().hex)
    destination.mkdir(parents=True)
    desktop = Path(__file__).resolve().parents[2] / 'apps/desktop'
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    built = subprocess.run(['node', 'scripts/runtime-build.cjs', '--profile', 'classroom-work-d4'], cwd=desktop,
        capture_output=True, text=True, encoding='utf-8', timeout=120, creationflags=flags)
    assert built.returncode == 0, built.stdout + built.stderr
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    result = subprocess.run(['node', 'tests/office-artifacts-integration.cjs'], cwd=desktop,
        env=dict(os.environ, CLASSMATTER_TEST_RUNTIME_ROOT=str(runtime.root), CLASSMATTER_TEST_SERVICE_PORT=str(port),
                 CLASSMATTER_TEST_DOWNLOAD_ROOT=str(destination)), capture_output=True, text=True, encoding='utf-8', timeout=120, creationflags=flags)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Document(str(destination / 'lesson.docx')).paragraphs[2].text == '认识分数。'
    assert Presentation(str(destination / 'lesson.pptx')).slides[1].shapes[0].text == '课堂目标'
