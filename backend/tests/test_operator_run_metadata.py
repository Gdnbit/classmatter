"""Private opt-in diagnostics cannot become a fact, leak content or block results."""
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from class_os.infrastructure.agent_diagnostics import RunDiagnostics
from class_os.infrastructure import operator_run_metadata as metadata


def packet():
    return {'run_id': str(uuid4()), 'outcome': 'failed', 'model_requests': 1, 'model_ms': 123, 'elapsed_ms': 150,
        'phase': 'model_loop', 'tool_calls': 0, 'model_steps': [{'request': 1, 'ms': 123, 'outcome': 'upstream_http'}],
        'category': 'upstream_http', 'http_status': 503, 'provider_status': 'UNAVAILABLE',
        'model_failure': {'category': 'upstream_http', 'http_status': 503, 'provider_status': 'UNAVAILABLE'}}


@pytest.mark.parametrize('profile,development,flag,enabled', [
    ('classroom-work-d4', True, None, False), ('classroom-work-d4', True, '1', True),
    ('classroom-work-d4', False, '1', False), ('workspace-chat-d3', True, '1', False),
    ('r1', True, '1', False), ('classroom-work-d4', True, 'true', False),
])
def test_logging_is_explicit_owned_development_only(tmp_path, monkeypatch, profile, development, flag, enabled):
    monkeypatch.delenv('CLASSMATTER_OPERATOR_METADATA', raising=False)
    if flag is not None: monkeypatch.setenv('CLASSMATTER_OPERATOR_METADATA', flag)
    sink = metadata.for_runtime(SimpleNamespace(root=tmp_path, profile=profile), local_development=development)
    assert bool(sink) is enabled and list(tmp_path.iterdir()) == []
    if enabled:
        value = packet(); sink(value)
        assert metadata.read_packets(tmp_path, [value['run_id']]) == [value]
        assert metadata.read_packets(tmp_path, [str(uuid4()), '../other', value['run_id'].upper()]) == []


@pytest.mark.parametrize('mistake', ['extra-content', 'phase-content', 'step-content', 'usage-content', 'error-body', 'wrong-status', 'path', 'boolean-counter'])
def test_unknown_fields_and_untrusted_strings_are_never_written(tmp_path, monkeypatch, mistake):
    monkeypatch.setenv('CLASSMATTER_OPERATOR_METADATA', '1')
    sink = metadata.for_runtime(SimpleNamespace(root=tmp_path, profile='classroom-work-d4'), local_development=True)
    value = packet(); canary = 'synthetic-private-content-must-never-be-recorded'
    if mistake == 'extra-content': value['prompt'] = canary
    if mistake == 'phase-content': value['phase'] = canary
    if mistake == 'step-content': value['model_steps'][0]['outcome'] = canary
    if mistake == 'usage-content': value['model_steps'][0]['input_tokens'] = canary
    if mistake == 'error-body': value['model_failure']['body'] = canary
    if mistake == 'wrong-status': value['model_failure']['provider_status'] = canary
    if mistake == 'path': value['run_id'] = '../other'
    if mistake == 'boolean-counter': value['model_ms'] = True
    assert metadata.valid_packet(value) is False
    sink(value); assert list(tmp_path.iterdir()) == []


def test_reports_are_bounded_exclusive_and_correlate_only_explicit_ids(tmp_path, monkeypatch):
    monkeypatch.setenv('CLASSMATTER_OPERATOR_METADATA', '1'); monkeypatch.setattr(metadata, 'MAX_REPORTS', 1)
    sink = metadata.for_runtime(SimpleNamespace(root=tmp_path, profile='classroom-work-d4'), local_development=True)
    value = packet(); sink(value)
    path = tmp_path / metadata.DIRECTORY / (value['run_id'] + '.json'); original = path.read_bytes()
    value['elapsed_ms'] = 999
    monkeypatch.setattr(metadata, 'MAX_REPORTS', 2)
    RunDiagnostics(sink, UUID(value['run_id'])).finish('completed')
    assert path.read_bytes() == original
    monkeypatch.setattr(metadata, 'MAX_REPORTS', 1)
    # A full/duplicate report is optional, not a reason to fail business work.
    RunDiagnostics(sink, uuid4()).finish('completed')
    assert path.read_bytes() == original and len(list(path.parent.iterdir())) == 1
    assert metadata.read_packets(tmp_path, [value['run_id']])[0]['elapsed_ms'] == 150
    assert metadata.read_packets(tmp_path, ['invalid'] * 50 + [value['run_id']]) == []
    path.write_text('{incomplete', encoding='utf-8')
    assert metadata.read_packets(tmp_path, [value['run_id']]) == []


def test_observer_io_failure_and_raw_provider_error_do_not_escape(tmp_path, monkeypatch):
    monkeypatch.setenv('CLASSMATTER_OPERATOR_METADATA', '1')
    (tmp_path / metadata.DIRECTORY).write_text('existing unrelated file', encoding='utf-8')
    sink = metadata.for_runtime(SimpleNamespace(root=tmp_path, profile='classroom-work-d4'), local_development=True)
    observer = RunDiagnostics(sink, uuid4())
    observer.finish('failed', ModelHTTPError(503, 'synthetic', {'error': {'message': 'synthetic-private-content'}}))
    assert (tmp_path / metadata.DIRECTORY).read_text() == 'existing unrelated file'
    assert metadata.read_packets(tmp_path, [str(uuid4())]) == []


def test_real_observer_serializes_no_exception_body(tmp_path, monkeypatch):
    monkeypatch.setenv('CLASSMATTER_OPERATOR_METADATA', '1')
    sink = metadata.for_runtime(SimpleNamespace(root=tmp_path, profile='classroom-work-d4'), local_development=True)
    request = uuid4()
    RunDiagnostics(sink, request).finish('failed', ModelHTTPError(503, 'synthetic', {'error': {'status': 'UNAVAILABLE', 'message': 'synthetic-private-content'}}))
    rows = metadata.read_packets(tmp_path, [str(request)])
    assert rows[0]['category'] == 'upstream_http' and 'synthetic-private-content' not in json.dumps(rows)


def test_directory_link_cannot_redirect_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv('CLASSMATTER_OPERATOR_METADATA', '1')
    other = tmp_path / 'outside'; other.mkdir()
    root = tmp_path / 'linked'; root.mkdir()
    try: (root / metadata.DIRECTORY).symlink_to(other, target_is_directory=True)
    except OSError: pytest.skip('Windows account lacks symlink privilege; ordinary path fence is tested separately')
    blocked = metadata.for_runtime(SimpleNamespace(root=root, profile='classroom-work-d4'), local_development=True)
    RunDiagnostics(blocked, uuid4()).finish('completed')
    assert list(other.iterdir()) == [] and metadata.read_packets(root, [str(uuid4())]) == []
