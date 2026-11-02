import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.exceptions import ModelHTTPError

from class_os.infrastructure.provider_evaluation import CASES, evaluate, compare, exact_json, offline_model, tools_for


async def test_twelve_offline_cases_are_runner_calibration_not_live_quality():
    report = await evaluate()
    assert len(CASES) == 12 and len({c.name for c in CASES}) == 12
    assert report['summary'] == {'passed': 12, 'quality-failed': 0, 'failed': 0, 'skipped-provider-unavailable': 0}
    assert not report['live'] and not report['formal_gate'] and not report['real_data'] and not report['business_writes']
    assert report['fixture_tools_not_qg']
    assert report['metrics']['observed_requests'] == 20
    assert compare(report, deepcopy(report)) == {'comparable': 12, 'regressions': [], 'improvements': []}


@pytest.mark.parametrize('text', ['{"count":true}', '{"count":1,"count":1}', '{"count":1,"extra":2}',
    '```json\n{"count":1}\n```', 'explanation {"count":1}', '{"count":NaN}'])
def test_exact_scoring_does_not_repair_or_accept_wrong_types(text):
    assert not exact_json(text, {'count': 1})


async def test_first_transport_fault_opens_circuit_and_drops_private_details():
    calls = []
    @asynccontextmanager
    async def fault(case):
        calls.append(case.name)
        raise httpx.ConnectError('synthetic-private-key-and-body-must-not-appear')
        yield
    report = await evaluate(fault)
    assert len(calls) == 1 and report['summary']['failed'] == 1 and report['summary']['skipped-provider-unavailable'] == 11
    assert report['metrics']['unknown_usage_cases'] == 1
    assert 'synthetic-private' not in json.dumps(report)


async def test_numeric_provider_error_is_diagnostic_without_publishing_body():
    @asynccontextmanager
    async def fault(case):
        raise ModelHTTPError(429, 'synthetic-model', {'error': {'code': '1305', 'message': 'synthetic-private-canary'}})
        yield
    report = await evaluate(fault)
    assert report['results'][0]['provider_error_code'] == '1305'
    assert report['results'][0]['http_status'] == 429
    assert 'synthetic-private' not in json.dumps(report)


async def test_quality_failure_does_not_disable_remaining_cases_or_create_false_pass():
    @asynccontextmanager
    async def wrong(case):
        if case is CASES[0]:
            yield FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart('{"open_tasks":99}')]))
        else:
            async with offline_model(case) as model:
                yield model
    report = await evaluate(wrong)
    assert report['summary']['quality-failed'] == 1 and report['summary']['passed'] == 11
    baseline = await evaluate()
    assert compare(baseline, report)['regressions'] == ['read_zh']


async def test_timeout_and_caller_cancellation_release_context_without_retry():
    entered, closed = asyncio.Event(), asyncio.Event()
    @asynccontextmanager
    async def slow(case):
        entered.set()
        try:
            await asyncio.Event().wait()
            yield
        finally:
            closed.set()
    report = await evaluate(slow, timeout=0.01)
    assert closed.is_set() and report['summary']['skipped-provider-unavailable'] == 11
    entered.clear()
    closed.clear()
    task = asyncio.create_task(evaluate(slow))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


async def test_contract_drift_blocks_before_any_provider_context(monkeypatch):
    from class_os.infrastructure import provider_evaluation as module
    original = module.for_mode
    def drift(*args):
        contracts = list(original(*args))
        if contracts:
            contracts[0]['description'] += ' unapproved'
        return contracts
    monkeypatch.setattr(module, 'for_mode', drift)
    @asynccontextmanager
    async def forbidden(case):
        pytest.fail('Must refuse contract drift before opening client')
        yield
    with pytest.raises(ValueError, match='contract drift'):
        await evaluate(forbidden)


def test_wrong_draft_arguments_cannot_be_hidden_by_correct_final_answer():
    calls = []
    tools = tools_for(CASES[6], calls)
    tools[0].function('wrong but valid synthetic title')
    from class_os.infrastructure.provider_evaluation import digest
    assert calls[0]['result_hash'] != digest(CASES[6].expected)
    with pytest.raises(ValueError):
        tools[0].function('second draft')


@pytest.mark.parametrize('field', ['case_digest', 'contract_digest', 'settings', 'limits', 'live'])
async def test_regression_comparison_rejects_changed_test_definition(field):
    before = await evaluate()
    after = deepcopy(before)
    after[field] = 'changed'
    with pytest.raises(ValueError):
        compare(before, after)


async def test_regression_comparison_refuses_missing_duplicate_and_all_skipped_rows():
    before = await evaluate()
    for rows in [before['results'][:-1], before['results'][:-1] + [before['results'][0]]]:
        after = deepcopy(before)
        after['results'] = rows
        with pytest.raises(ValueError):
            compare(before, after)
    skipped = deepcopy(before)
    for row in skipped['results']:
        row['status'] = 'skipped-provider-unavailable'
    with pytest.raises(ValueError):
        compare(before, skipped)


@pytest.mark.parametrize('args', [['live'], ['offline', '--local-google-key'], ['offline', '--proxy', 'http://127.0.0.1:7890']])
def test_cli_cannot_load_secrets_or_network_without_explicit_live_confirmation(args):
    script = Path(__file__).resolve().parents[1] / 'provider_eval.py'
    result = subprocess.run([sys.executable, str(script), *args], capture_output=True, timeout=10)
    assert result.returncode == 2


def test_cli_never_echoes_accidental_key_or_accepts_paid_fallback():
    script = Path(__file__).resolve().parents[1] / 'provider_eval.py'
    for args in [['live', '--api-key', 'synthetic-private-cli-canary'], ['live', '--provider', 'paid-fallback-canary']]:
        result = subprocess.run([sys.executable, str(script), *args], capture_output=True, timeout=10)
        assert result.returncode == 2
        assert b'synthetic-private-cli-canary' not in result.stderr and b'paid-fallback-canary' not in result.stderr
