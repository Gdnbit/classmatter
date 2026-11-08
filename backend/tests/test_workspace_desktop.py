"""Original Electron shell with an isolated D3 owned database, no real provider."""
import os
from pathlib import Path
import socket
import subprocess

import pytest
from class_os.infrastructure.workspace_upgrade import upgrade_workspace_chat
from test_workbench_upgrade import owned_upgrade


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows Electron/DPAPI runtime')
def test_workspace_chat_survives_native_application_restart(owned_upgrade):
    current = upgrade_workspace_chat(owned_upgrade.runtime)
    desktop = Path(__file__).resolve().parents[2] / 'apps/desktop'
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    build = subprocess.run(['node', 'scripts/runtime-build.cjs', '--profile', 'workspace-chat-d3'], cwd=desktop,
        capture_output=True, text=True, encoding='utf-8', timeout=60, creationflags=creationflags)
    assert build.returncode == 0, build.stdout + build.stderr
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    result = subprocess.run(['node', 'tests/workspace-chat-integration.cjs'], cwd=desktop,
        env=dict(os.environ, CLASSMATTER_TEST_RUNTIME_ROOT=str(current.root), CLASSMATTER_TEST_SERVICE_PORT=str(port)),
        capture_output=True, text=True, encoding='utf-8', timeout=130, creationflags=creationflags)
    assert result.returncode == 0, result.stdout + result.stderr
