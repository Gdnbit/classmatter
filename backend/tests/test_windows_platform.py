"""Optional OS metadata fallback; no service, dependency or permission changes."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from class_os.infrastructure import windows_platform as adapter


@pytest.mark.parametrize('value', [None, '0'])
def test_default_preserves_existing_platform_query(monkeypatch, value):
    original = lambda *_args: 'original metadata'
    metadata = SimpleNamespace(_wmi_query=original)
    monkeypatch.setattr(adapter, 'platform', metadata)
    monkeypatch.setattr(adapter, 'sys', SimpleNamespace(platform='win32'))
    assert adapter.configure_windows_platform({} if value is None else {'CLASSMATTER_WINDOWS_METADATA_FALLBACK': value}) is False
    assert metadata._wmi_query is original


@pytest.mark.parametrize('value', ['', 'yes', '2'])
def test_invalid_option_cannot_silently_change_metadata(monkeypatch, value):
    metadata = SimpleNamespace()
    monkeypatch.setattr(adapter, 'platform', metadata)
    with pytest.raises(ValueError, match='must be 0 or 1'):
        adapter.configure_windows_platform({'CLASSMATTER_WINDOWS_METADATA_FALLBACK': value})
    assert not vars(metadata)


def test_non_windows_option_does_not_patch_metadata(monkeypatch):
    metadata = SimpleNamespace()
    monkeypatch.setattr(adapter, 'platform', metadata)
    monkeypatch.setattr(adapter, 'sys', SimpleNamespace(platform='linux'))
    assert adapter.configure_windows_platform({'CLASSMATTER_WINDOWS_METADATA_FALLBACK': '1'}) is False
    assert not vars(metadata)


def test_unsupported_runtime_is_reported_without_fake_values(monkeypatch):
    monkeypatch.setattr(adapter, 'platform', SimpleNamespace())
    monkeypatch.setattr(adapter, 'sys', SimpleNamespace(platform='win32'))
    with pytest.raises(RuntimeError, match='no supported optional WMI query'):
        adapter.configure_windows_platform({'CLASSMATTER_WINDOWS_METADATA_FALLBACK': '1'})


def test_opt_in_selects_oserror_fallback_and_is_idempotent(monkeypatch):
    metadata = SimpleNamespace(_wmi_query=lambda *_args: 'unused')
    monkeypatch.setattr(adapter, 'platform', metadata)
    monkeypatch.setattr(adapter, 'sys', SimpleNamespace(platform='win32'))
    option = {'CLASSMATTER_WINDOWS_METADATA_FALLBACK': '1'}
    assert adapter.configure_windows_platform(option) is True
    first = metadata._wmi_query
    with pytest.raises(OSError, match='Optional WMI metadata'):
        first('os', 'Version')
    assert adapter.configure_windows_platform(option) is True
    assert metadata._wmi_query is first


@pytest.mark.parametrize('option', [None, '0'])
def test_fresh_default_adapter_import_preserves_platform(option):
    source = Path(__file__).resolve().parents[1] / 'src'
    environment = dict(os.environ)
    environment.pop('CLASSMATTER_WINDOWS_METADATA_FALLBACK', None)
    if option is not None:
        environment['CLASSMATTER_WINDOWS_METADATA_FALLBACK'] = option
    code = '''
import platform, sys
sys.path.insert(0, sys.argv[1])
def unchanged(*args):
    raise AssertionError('Metadata must not be queried during adapter import')
platform._wmi_query = unchanged
import class_os.infrastructure
assert platform._wmi_query is unchanged
print('unchanged')
'''
    result = subprocess.run([sys.executable, '-I', '-c', code, str(source)],
        env=environment, capture_output=True, text=True, encoding='utf-8', timeout=15,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'unchanged'


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows standard-library fallback')
@pytest.mark.parametrize('entry', ['explicit', 'adapter-import'])
def test_fresh_process_uses_real_os_fallback_and_native_sqlalchemy(entry):
    source = Path(__file__).resolve().parents[1] / 'src'
    code = '''
import json, os, platform, sys
sys.path.insert(0, sys.argv[1])
def unexpected_wmi(*args):
    raise AssertionError('The unavailable optional WMI query must not run')
platform._wmi_query = unexpected_wmi
if sys.argv[2] == 'explicit':
    from class_os.infrastructure.windows_platform import configure_windows_platform
    assert configure_windows_platform(os.environ)
else:
    import class_os.infrastructure.conversation_restrictions
import sqlalchemy
from sqlalchemy.util._has_cy import HAS_CYEXTENSION
assert HAS_CYEXTENSION
assert platform.system() == 'Windows'
assert platform.machine() == 'AMD64'
assert platform.win32_ver()[1]
print(json.dumps({'native_extensions': HAS_CYEXTENSION, 'version': sqlalchemy.__version__}))
'''
    result = subprocess.run([sys.executable, '-I', '-c', code, str(source), entry],
        env=dict(os.environ, CLASSMATTER_WINDOWS_METADATA_FALLBACK='1'),
        capture_output=True, text=True, encoding='utf-8', timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'native_extensions': True, 'version': '2.0.54'}
