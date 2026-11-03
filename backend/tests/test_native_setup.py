"""Native-only human setup adapter; only owned disposable synthetic roots."""
import json
import os
from pathlib import Path
import subprocess
import sys
import socket
import secrets

import pytest
from sqlalchemy import text

from class_os.infrastructure.local_runtime import LocalRuntime
from class_os.infrastructure.native_setup import NativeSetup


@pytest.mark.parametrize('payload', [None, [], {}, {'operation': 'ddl', 'sql': 'DROP'},
    {'operation': 'create_owner', 'password': 'synthetic-private-canary', 'extra': True},
    {'operation': 'create_owner', 'password': 'short'},
    {'operation': 'approve_control', 'operation_id': 'synthetic', 'payload_hash': 'synthetic', 'confirmed': 1}])
def test_closed_requests_fail_before_any_authority_or_runtime_access(payload):
    setup = NativeSetup.__new__(NativeSetup)
    setup.proposal = None
    with pytest.raises(ValueError):
        setup.handle(payload)


def test_private_entry_has_no_default_proof_or_credential_argument(tmp_path):
    entry = Path(__file__).resolve().parents[1] / 'desktop_setup.py'
    for env, args in [(dict(os.environ, CLASSMATTER_SETUP_PROCESS_KEY=''), []),
                      (dict(os.environ, CLASSMATTER_SETUP_PROCESS_KEY='12' * 32), ['--password', 'synthetic-private-canary'])]:
        result = subprocess.run([sys.executable, str(entry), *args], cwd=tmp_path,
            env=env, input='synthetic-private-canary', capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode != 0 and result.stdout == '' and result.stderr == ''
    assert list(tmp_path.iterdir()) == []


def test_development_identity_requires_explicit_trusted_flag():
    setup = NativeSetup.__new__(NativeSetup)
    setup.development = False
    with pytest.raises(ValueError, match='Explicit local development'):
        setup.handle({'operation': 'development_access'})


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows Electron/DPAPI development entry')
def test_passwordless_development_uses_original_identity_and_preserves_restart(tmp_path, request):
    repository = Path(__file__).resolve().parents[2]
    desktop = repository / 'apps/desktop'
    built = subprocess.run(['node', 'scripts/runtime-build.cjs', '--profile', 'conversation-d1'],
        cwd=desktop, capture_output=True, timeout=90,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert built.returncode == 0, 'Desktop build failed'
    runtime = LocalRuntime(tmp_path / 'passwordless-development', profile='conversation-d1')
    runtime.initialize(request.config.getoption('--pg-root'))
    runtime.start()
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        result = subprocess.run(['node', 'tests/development-integration.cjs'], cwd=desktop,
            env=dict(os.environ, CLASSMATTER_TEST_RUNTIME_ROOT=str(runtime.root),
                     CLASSMATTER_TEST_SERVICE_PORT=str(port)),
            capture_output=True, text=True, encoding='utf-8', timeout=120,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr
        assert (runtime.root / 'developer-identity.dpapi').is_file()
        with runtime.database('identity').transaction(read_only=True) as connection:
            assert connection.execute(text('SELECT count(*) FROM class_os.owner_account')).scalar_one() == 1
    finally:
        runtime.stop()


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows Electron/DPAPI first-run UI')
def test_original_shell_opens_after_native_human_setup(tmp_path, request):
    repository = Path(__file__).resolve().parents[2]
    desktop = repository / 'apps/desktop'
    built = subprocess.run(['node', 'scripts/runtime-build.cjs', '--profile', 'conversation-d1'],
        cwd=desktop, capture_output=True, timeout=90,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert built.returncode == 0, 'Desktop build failed'
    runtime = LocalRuntime(tmp_path / 'first-run-ui', profile='conversation-d1')
    runtime.initialize(request.config.getoption('--pg-root'))
    runtime.start()
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        result = subprocess.run(['node', 'tests/setup-integration.cjs'], cwd=desktop,
            env=dict(os.environ, CLASSMATTER_TEST_RUNTIME_ROOT=str(runtime.root),
                     CLASSMATTER_TEST_SERVICE_PORT=str(port)),
            capture_output=True, text=True, encoding='utf-8', timeout=100,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stdout + result.stderr
        setup = NativeSetup(runtime)
        try:
            assert setup.status() == {'owner_present': True, 'ready': True}
        finally:
            setup.close()
    finally:
        runtime.stop()


@pytest.mark.db
@pytest.mark.skipif(os.name != 'nt', reason='Current-user DPAPI native setup')
def test_real_isb_then_explicit_control_preview_approval_and_same_receipt(tmp_path, request):
    runtime = LocalRuntime(tmp_path / 'owned-native-setup', profile='conversation-d1')
    runtime.initialize(request.config.getoption('--pg-root'))
    runtime.start()
    setup = NativeSetup(runtime)
    try:
        assert setup.handle({'operation': 'status'}) == {'owner_present': False, 'ready': False}
        password = secrets.token_urlsafe(24)
        kit = setup.handle({'operation': 'create_owner', 'password': password})
        assert len(kit['recovery_codes']) == len(set(kit['recovery_codes'])) == 5
        assert setup.status() == {'owner_present': True, 'ready': False}
        development = NativeSetup(runtime, development=True)
        with pytest.raises(ValueError, match='Existing personal identity'):
            development.development_access()
        assert not (runtime.root / 'developer-identity.dpapi').exists()
        with pytest.raises(ValueError):
            setup.create_owner(password)
        preview = setup.handle({'operation': 'preview_control', 'password': password})
        assert preview['risk'] == 'X' and preview['payload']['command'] == 'conversation.control.initialize'
        assert 'recovery_codes' not in preview and password not in json.dumps(preview)
        for changed in [{'confirmed': False}, {'payload_hash': '0' * 64}, {'operation_id': 'wrong'}]:
            with pytest.raises(ValueError):
                setup.handle({'operation': 'approve_control', 'operation_id': preview['operation_id'],
                    'payload_hash': preview['payload_hash'], 'confirmed': True, **changed})
        assert not setup.status()['ready']
        command = {'operation': 'approve_control', 'operation_id': preview['operation_id'],
                   'payload_hash': preview['payload_hash'], 'confirmed': True}
        receipt = setup.handle(command)
        assert setup.handle(command) == receipt and receipt['ready'] is True
        assert setup.status() == {'owner_present': True, 'ready': True}
        database = runtime.database('runtime')
        try:
            with database.transaction(read_only=True) as connection:
                assert connection.execute(text('SELECT count(*) FROM class_os.conversation_control')).scalar_one() == 1
                assert connection.execute(text('SELECT count(*) FROM class_os.command_receipt')).scalar_one() == 1
                for table in ['student', 'record_revision', 'manual_task', 'conversation_run', 'model_configuration']:
                    assert connection.execute(text('SELECT count(*) FROM class_os.' + table)).scalar_one() == 0
        finally:
            database.close()
    finally:
        setup.close()
        runtime.stop()
