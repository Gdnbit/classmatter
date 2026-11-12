"""Boundary evidence is intentionally narrower than root-cause attribution."""
import asyncio
import json
import socket
import ssl

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from class_os.infrastructure.agent_diagnostics import RunDiagnostics, classify_failure


@pytest.mark.parametrize('error,category', [
    (httpx.ProxyError('private'), 'network_proxy'),
    (socket.gaierror('private'), 'network_dns'),
    (ssl.SSLError('private'), 'network_tls'),
    (httpx.ConnectTimeout('private'), 'network_connect_timeout'),
    (httpx.ReadTimeout('private'), 'network_read_timeout'),
    (httpx.WriteTimeout('private'), 'network_write_timeout'),
    (httpx.PoolTimeout('private'), 'local_connection_pool'),
    (httpx.ConnectError('private'), 'network_connect'),
    (TimeoutError('private'), 'timeout_unattributed'),
    (UsageLimitExceeded('private'), 'local_usage_limit'),
    (UnexpectedModelBehavior('private'), 'model_contract'),
    (RuntimeError('private'), 'unclassified'),
    (asyncio.CancelledError(), 'cancelled'),
])
def test_closed_failure_classification(error, category):
    assert classify_failure(error) == {'category': category}
    assert 'private' not in json.dumps(classify_failure(error))


def test_http_signal_is_not_an_invented_provider_root_cause():
    error = ModelHTTPError(504, 'private-model', body='<html>private proxy</html>')
    assert classify_failure(error) == {'category': 'upstream_http', 'http_status': 504}
    error = ModelHTTPError(503, 'private-model', body={'error': {'status': 'UNAVAILABLE', 'message': 'private'}})
    assert classify_failure(error) == {'category': 'upstream_http', 'http_status': 503, 'provider_status': 'UNAVAILABLE'}
    error = ModelHTTPError(429, 'private-model', body={'error': {'status': 'private', 'message': 'private'}})
    assert classify_failure(error) == {'category': 'upstream_rate_limit', 'http_status': 429}


def test_nested_dns_and_tls_and_cycles():
    wrapper = httpx.ConnectError('private')
    wrapper.__cause__ = socket.gaierror('private')
    assert classify_failure(wrapper)['category'] == 'network_dns'
    wrapper.__cause__ = ssl.SSLError('private')
    assert classify_failure(wrapper)['category'] == 'network_tls'
    wrapper.__cause__ = wrapper
    assert classify_failure(wrapper)['category'] == 'network_connect'


async def test_real_sdk_hook_counts_requests_without_observer_affecting_result():
    reports = []
    diagnostic = RunDiagnostics(reports.append, 'opaque-request')
    agent = Agent(FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart('private answer')])), capabilities=[diagnostic])
    assert (await agent.run('private prompt')).output == 'private answer'
    diagnostic.finish('completed')
    assert reports[0]['model_requests'] == 1 and reports[0]['outcome'] == 'completed'
    assert len(reports[0]['model_steps']) == 1 and reports[0]['model_steps'][0]['outcome'] == 'completed'
    assert 'private' not in json.dumps(reports)
    def broken(packet):
        raise RuntimeError('observer outage')
    diagnostic.sink = broken
    diagnostic.finish('completed')


async def test_sdk_failure_preserves_wire_timeout_and_run_budget_separately():
    async def fail(messages, info):
        raise httpx.ReadTimeout('private url and key')
    reports = []
    diagnostic = RunDiagnostics(reports.append, 'opaque-request')
    agent = Agent(FunctionModel(fail), capabilities=[diagnostic])
    with pytest.raises(httpx.ReadTimeout):
        await agent.run('private prompt')
    diagnostic.finish('failed', TimeoutError(), deadline_expired=True)
    assert reports[0]['category'] == 'local_run_deadline'
    assert reports[0]['model_failure'] == {'category': 'network_read_timeout'}
    assert reports[0]['model_requests'] == 1
    assert 'private' not in json.dumps(reports)


async def test_concurrent_runs_do_not_share_failure_or_timing_state():
    reports = []
    async def one(run_id, fail):
        async def respond(messages, info):
            await asyncio.sleep(.01)
            if fail:
                raise httpx.ConnectError('private')
            return ModelResponse(parts=[TextPart('ok')])
        diagnostic = RunDiagnostics(reports.append, run_id)
        try:
            await Agent(FunctionModel(respond), capabilities=[diagnostic]).run('private')
            diagnostic.finish('completed')
        except httpx.ConnectError as error:
            diagnostic.finish('failed', error)
    await asyncio.gather(one('first', True), one('second', False))
    by_run = {report['run_id']: report for report in reports}
    assert by_run['first']['category'] == 'network_connect'
    assert 'category' not in by_run['second'] and by_run['second']['outcome'] == 'completed'
    assert all(report['model_requests'] == len(report['model_steps']) == 1 for report in reports)
