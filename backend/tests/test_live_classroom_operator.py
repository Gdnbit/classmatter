"""CI must never execute the real-model/native operator implicitly."""
import json
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('case', ['failed', 'pending', 'wrong-source', 'wrong-student', 'other-pending', 'already-saved', 'other-request', 'paginated', 'duplicate-fact', 'documents', 'receipt-mismatch'])
def test_daily_recovery_requires_the_original_receipt_and_exact_unsaved_followup(case):
    import importlib.util
    spec = importlib.util.spec_from_file_location('live_operator_checkpoint', Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    fact = {'record_id': 'record-1', 'student_id': 'student-1'}
    first = {'candidate': {'command': 'record.create'}, 'action_receipt': {'resource_id': 'record-1'}}
    last = {'state': 'completed', 'user_text': '继续完成上面的任务，只处理尚未完成的步骤。',
        'candidate': {'command': 'task.create', 'title': '合成作品核对', 'source_record_id': 'record-1', 'student_id': 'student-1'}, 'action_receipt': None}
    history = {'thread': {'status': 'active'}, 'next_before': None, 'turns': [first, last]}
    world, documents = {'records': [fact], 'tasks': []}, []
    if case == 'failed': last.update(state='failed', candidate=None)
    if case == 'wrong-source': last['candidate']['source_record_id'] = 'other-record'
    if case == 'wrong-student': last['candidate']['student_id'] = 'other-student'
    if case == 'other-pending': history['turns'].insert(1, dict(last, candidate={'command': 'document.create'}))
    if case == 'already-saved': world['tasks'].append({'task_id': 'existing'})
    if case == 'other-request': last['user_text'] = '其他请求'
    if case == 'paginated': history['next_before'] = 1
    if case == 'duplicate-fact': world['records'].append(dict(fact))
    if case == 'documents': documents.append({'document_id': 'existing'})
    if case == 'receipt-mismatch': first['action_receipt']['resource_id'] = 'other-record'
    assert module.daily_recovery_checkpoint(history, world, documents) is (case in ('failed', 'pending'))


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
@pytest.mark.parametrize('scenario', ['classroom-recovery', 'daily-work-recovery'])
def test_recovery_needs_both_fixture_and_explicit_thread_before_io(tmp_path, extra, scenario):
    entry = Path(__file__).resolve().parents[1] / 'live_classroom_acceptance.py'
    result = subprocess.run([sys.executable, str(entry), '--live', '--scenario', scenario,
        '--source-runtime-root', str(tmp_path/'source'), '--pg-root', str(tmp_path/'pg'), *extra],
        cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {'status': 'blocked', 'reason': 'explicit_recovery_fixture_and_thread_required', 'requests': 0}
    assert result.stderr == '' and list(tmp_path.iterdir()) == []
