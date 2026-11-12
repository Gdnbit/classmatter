"""CI must never execute the real-model/native operator implicitly."""
import json
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('arguments', [[], ['--live'], ['--scenario', 'daily-work'], ['--live', '--scenario', 'daily-work'], ['--scenario', 'full-workbench'], ['--live', '--scenario', 'full-workbench'], ['--scenario', 'classroom-documents'], ['--live', '--scenario', 'classroom-documents']])
def test_live_classroom_operator_denies_incomplete_invocation_before_io(tmp_path, arguments):
    entry = Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py'
    result = subprocess.run([sys.executable, str(entry), *arguments], cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout)['requests'] == 0
    assert result.stderr == '' and list(tmp_path.iterdir()) == []


def test_live_classroom_operator_does_not_echo_an_accidental_key(tmp_path):
    entry = Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py'
    canary = 'synthetic-argument-must-not-be-logged'
    result = subprocess.run([sys.executable, str(entry), '--key', canary], cwd=tmp_path,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert canary not in result.stdout + result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('root', ['relative', 'C:/synthetic-not-created', '//fixture.invalid/share'])
def test_live_operator_refuses_system_relative_or_remote_artifact_roots_before_io(tmp_path, root):
    entry = Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py'
    result = subprocess.run([sys.executable, str(entry), '--live', '--provider', 'zhipu',
        '--source-runtime-root', str(tmp_path/'source'), '--pg-root', str(tmp_path/'pg'), '--artifacts-root', root],
        cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2 and json.loads(result.stdout)['requests'] == 0
    assert json.loads(result.stdout)['reason'] == 'non_system_local_artifacts_root_required'
    assert result.stderr == '' and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('scenario,reason', [('full-workbench', 'full_workbench_requires_fresh_fixture'), ('daily-work', 'daily_work_requires_fresh_fixture')])
def test_full_workbench_refuses_resume_before_reading_credentials_or_creating_files(tmp_path, scenario, reason):
    entry = Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py'
    result = subprocess.run([sys.executable, str(entry), '--live', '--scenario', scenario,
        '--source-runtime-root', str(tmp_path/'source'), '--pg-root', str(tmp_path/'pg'), '--resume-runtime-root', str(tmp_path/'old')],
        cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {'status': 'blocked', 'reason': reason, 'requests': 0}
    assert result.stderr == '' and list(tmp_path.iterdir()) == []


def test_invalid_free_model_or_pacing_is_rejected_before_io(tmp_path):
    entry = Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py'
    for arguments in (['--provider', 'unreviewed-paid-model'], ['--turn-interval-seconds', '-1'], ['--turn-interval-seconds', '3600']):
        result = subprocess.run([sys.executable, str(entry), *arguments], cwd=tmp_path,
            capture_output=True, text=True, timeout=15)
        assert result.returncode == 2 and result.stdout == ''
        assert 'Invalid acceptance options' in result.stderr
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('extra', [[], ['--resume-runtime-root', 'unused'], ['--resume-thread-id', '00000000-0000-0000-0000-000000000001']])
def test_recovery_needs_both_fixture_and_explicit_thread_before_io(tmp_path, extra):
    entry = Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py'
    result = subprocess.run([sys.executable, str(entry), '--live', '--scenario', 'classroom-recovery',
        '--source-runtime-root', str(tmp_path/'source'), '--pg-root', str(tmp_path/'pg'), *extra],
        cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {'status': 'blocked', 'reason': 'explicit_recovery_fixture_and_thread_required', 'requests': 0}
    assert result.stderr == '' and list(tmp_path.iterdir()) == []
