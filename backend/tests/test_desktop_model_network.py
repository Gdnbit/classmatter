"""Trusted launch composition, never remote inference or an existing instance."""
import importlib.util
from pathlib import Path
import sys
import os
import socket
import subprocess

import pytest

from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings

GOOGLE = 'https://generativelanguage.googleapis.com/v1beta/openai/'


def operator():
    path = Path(__file__).resolve().parents[1] / 'desktop.py'
    spec = importlib.util.spec_from_file_location('desktop_model_operator_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('profile', ['r1', 'conversation-d1'])
def test_explicit_transport_reaches_existing_composition_without_enable_or_new_storage(monkeypatch, profile):
    from class_os.infrastructure import local_runtime, durable_local_runtime
    from class_os.interfaces.http import web
    import uvicorn
    module = operator()
    seen = []
    def compose(settings, runtime):
        seen.append(settings)
        return create_app(settings)
    monkeypatch.setattr(local_runtime, 'LocalRuntime', lambda *a, **kw: object())
    monkeypatch.setattr(local_runtime, 'compose', compose)
    monkeypatch.setattr(durable_local_runtime, 'compose', compose)
    monkeypatch.setattr(web, 'mount_web', lambda *a: None)
    monkeypatch.setattr(uvicorn.Server, 'run', lambda self: None)
    monkeypatch.setenv('CLASSMATTER_DESKTOP_PROCESS_KEY', '12' * 32)
    monkeypatch.setattr(sys, 'argv', ['desktop.py', '--ui-root', 'synthetic-not-read', '--profile', profile,
        '--model-api-base-url', GOOGLE, '--model-api-proxy', 'http://127.0.0.1:7890'])
    module.main()
    assert len(seen) == 1
    assert seen[0].model_api_bases == (GOOGLE,) and seen[0].model_api_proxy == 'http://127.0.0.1:7890'
    assert seen[0].model_provider == 'fake' and seen[0].mode == 'synthetic-development'


@pytest.mark.parametrize('flags', [
    ['--model-api-base-url', GOOGLE + '?api_key=synthetic-private-canary'],
    ['--model-api-base-url', GOOGLE, '--model-api-base-url', GOOGLE],
    ['--model-api-base-url', GOOGLE, '--model-api-proxy', 'http://remote.invalid:7890'],
    ['--model-api-proxy', 'http://127.0.0.1:7890'],
])
def test_invalid_transport_is_refused_before_runtime_access(monkeypatch, flags):
    from class_os.infrastructure import local_runtime
    module = operator()
    monkeypatch.setenv('CLASSMATTER_DESKTOP_PROCESS_KEY', '12' * 32)
    monkeypatch.setattr(local_runtime, 'LocalRuntime', lambda *a, **kw: pytest.fail('Must not read/init a runtime'))
    monkeypatch.setattr(sys, 'argv', ['desktop.py', '--ui-root', 'synthetic-not-read', *flags])
    with pytest.raises(Exception) as error:
        module.main()
    assert 'synthetic-private-canary' not in str(error.value)


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows Electron/DPAPI operator')
def test_actual_desktop_startup_permission_is_transient_and_never_auto_calls_model(tmp_path, request):
    from class_os.infrastructure.local_runtime import LocalRuntime
    from class_os.application.identity import IdentityBoundary
    from class_os.infrastructure.identity import PostgresIdentityStore
    from pwdlib import PasswordHash
    from sqlalchemy import text
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 8000))
        except OSError:
            pytest.skip('Existing port8000 listener preserved')
    desktop = Path(__file__).resolve().parents[2] / 'apps/desktop'
    built = subprocess.run(['node', 'scripts/runtime-build.cjs'], cwd=desktop, capture_output=True, timeout=60)
    assert built.returncode == 0
    runtime = LocalRuntime(tmp_path / 'owned-model-transport')
    runtime.initialize(request.config.getoption('--pg-root'))
    runtime.start()
    identity = runtime.database('identity')
    try:
        boundary = IdentityBoundary(PostgresIdentityStore(identity), PasswordHash.recommended())
        client = 'synthetic-desktop-model-fixture-client'
        owner = boundary.bootstrap(boundary.arm_bootstrap(), 'synthetic-test-passphrase-2026', client)
        boundary.logout(owner.token, client, owner.csrf)
        result = subprocess.run(['node', 'tests/runtime-model-network.cjs'], cwd=desktop,
            env=dict(os.environ, CLASSMATTER_TEST_RUNTIME_ROOT=str(runtime.root)), capture_output=True,
            text=True, encoding='utf-8', timeout=100, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr
        database = runtime.database('runtime')
        try:
            with database.transaction(read_only=True) as connection:
                assert connection.execute(text('SELECT count(*) FROM class_os.model_configuration WHERE sealed IS NOT NULL')).scalar_one() == 1
                assert connection.execute(text("SELECT count(*) FROM class_os.business_audit WHERE action IN ('model.test.started','model.invoke','model.enable')")).scalar_one() == 0
        finally:
            database.close()
    finally:
        identity.close()
        runtime.stop()
