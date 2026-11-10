"""CI must never execute the real-model/native operator implicitly."""
import json
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('arguments', [[], ['--live'], ['--scenario', 'full-workbench'], ['--live', '--scenario', 'full-workbench']])
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


def test_full_workbench_refuses_resume_before_reading_credentials_or_creating_files(tmp_path):
    entry = Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py'
    result = subprocess.run([sys.executable, str(entry), '--live', '--scenario', 'full-workbench',
        '--source-runtime-root', str(tmp_path/'source'), '--pg-root', str(tmp_path/'pg'), '--resume-runtime-root', str(tmp_path/'old')],
        cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {'status': 'blocked', 'reason': 'full_workbench_requires_fresh_fixture', 'requests': 0}
    assert result.stderr == '' and list(tmp_path.iterdir()) == []
