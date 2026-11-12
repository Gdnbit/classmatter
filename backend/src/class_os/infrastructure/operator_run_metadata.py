"""Opt-in bounded metadata for an owned synthetic development instance only."""
import json
import os
from itertools import islice
from pathlib import Path
from uuid import UUID

MAX_REPORTS = 1000
MAX_BYTES = 4096
DIRECTORY = 'operator-run-metadata'
CATEGORIES = frozenset(('network_proxy', 'network_dns', 'network_tls', 'network_connect_timeout',
    'network_read_timeout', 'network_write_timeout', 'local_connection_pool', 'network_connect',
    'network_read', 'network_write', 'network_protocol', 'upstream_rate_limit', 'upstream_http',
    'local_usage_limit', 'timeout_unattributed', 'model_contract', 'unclassified', 'cancelled', 'local_run_deadline'))
PHASES = frozenset(('audit_start', 'tool_contract', 'provider_binding', 'model_loop',
    'response_validation', 'audit_completion', 'completed', 'persistence_claim', 'history_read', 'sdk_dispatch', 'persistence_finish'))
PERSISTENCE_PHASES = frozenset(('persistence_claim', 'history_read', 'sdk_dispatch', 'persistence_finish'))
SIGNALS = frozenset(('UNAVAILABLE', 'DEADLINE_EXCEEDED', 'RESOURCE_EXHAUSTED', 'INTERNAL',
    'INVALID_ARGUMENT', 'PERMISSION_DENIED', 'UNAUTHENTICATED', 'NOT_FOUND'))
LIMITS = frozenset(('request_limit', 'tool_calls_limit', 'input_tokens_limit', 'output_tokens_limit', 'total_tokens_limit'))


def _failure(value):
    return (type(value) is dict and not set(value) - {'category', 'http_status', 'provider_status', 'limit'}
        and value.get('category') in CATEGORIES
        and ('http_status' not in value or type(value['http_status']) is int and 100 <= value['http_status'] <= 599)
        and ('provider_status' not in value or value['provider_status'] in SIGNALS)
        and ('limit' not in value or value['limit'] in LIMITS))


def valid_packet(value):
    base = {'run_id', 'outcome', 'model_requests', 'model_ms', 'elapsed_ms', 'phase', 'tool_calls', 'model_steps'}
    if (type(value) is not dict or not base <= set(value)
            or set(value) - base - {'category', 'http_status', 'provider_status', 'limit', 'model_failure'}):
        return False
    try:
        if type(value['run_id']) is not str or str(UUID(value['run_id'])) != value['run_id']:
            return False
        if value['outcome'] not in ('completed', 'failed', 'cancelled') or value['phase'] not in PHASES:
            return False
        if any(type(value[key]) is not int or not 0 <= value[key] <= 3600000 for key in ('model_requests', 'model_ms', 'elapsed_ms', 'tool_calls')):
            return False
        if type(value['model_steps']) is not list or len(value['model_steps']) > 10:
            return False
        for step in value['model_steps']:
            if (type(step) is not dict or not {'request', 'ms', 'outcome'} <= set(step)
                    or set(step) - {'request', 'ms', 'outcome', 'input_tokens', 'output_tokens'}
                    or type(step['request']) is not int or not 1 <= step['request'] <= 10
                    or type(step['ms']) is not int or not 0 <= step['ms'] <= 3600000
                    or any(type(step[key]) is not int or not 0 <= step[key] <= 2147483647 for key in ('input_tokens', 'output_tokens') if key in step)
                    or step['outcome'] not in CATEGORIES | {'completed'}):
                return False
        failure = {key: value[key] for key in ('category', 'http_status', 'provider_status', 'limit') if key in value}
        return ((not failure or _failure(failure))
            and ('model_failure' not in value or _failure(value['model_failure'])))
    except (ValueError, TypeError):
        return False


def _directory(root):
    root = Path(root).resolve(strict=True)
    directory = root / DIRECTORY
    if directory.is_symlink() or directory.exists() and (not directory.is_dir() or directory.resolve().parent != root):
        raise ValueError('Owned metadata directory required')
    return directory


def for_runtime(runtime, *, local_development):
    if not local_development or runtime.profile != 'classroom-work-d4' or os.environ.get('CLASSMATTER_OPERATOR_METADATA') != '1':
        return None
    root = runtime.root
    def write(packet):
        if not valid_packet(packet):
            return
        data = json.dumps(packet, ensure_ascii=True, separators=(',', ':')).encode()
        if len(data) > MAX_BYTES:
            return
        directory = _directory(root); directory.mkdir(mode=0o700, exist_ok=True)
        if sum(1 for entry in directory.iterdir() if entry.suffix == '.json') >= MAX_REPORTS:
            return
        # Exclusive create never replaces a previous report or follows a file link.
        suffix = '.persistence.json' if packet['phase'] in PERSISTENCE_PHASES else '.json'
        with (directory / (packet['run_id'] + suffix)).open('xb') as target:
            target.write(data)
    return write


def read_packets(root, request_ids):
    """Read only the explicitly observed request UUIDs, never arbitrary files."""
    result = []
    try:
        directory = _directory(root)
    except (OSError, ValueError):
        return result
    for request in islice(request_ids, 50):
        try:
            if type(request) is not str or str(UUID(request)) != request:
                continue
        except (ValueError, TypeError):
            continue
        for suffix in ('.json', '.persistence.json'):
            try:
                path = directory / (request + suffix)
                if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
                    continue
                packet = json.loads(path.read_bytes())
                if (valid_packet(packet) and packet['run_id'] == request
                        and (packet['phase'] in PERSISTENCE_PHASES) == (suffix == '.persistence.json')):
                    result.append(packet)
            except (OSError, ValueError, TypeError, RecursionError):
                continue
    return result
