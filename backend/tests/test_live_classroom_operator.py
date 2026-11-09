"""CI must never execute the real-model/native operator implicitly."""
import json
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('arguments', [[], ['--live']])
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
