"""12 synthetic scenarios: offline boundary regression vs optional live quality.

The operator uses these same owned disposable PostgreSQL fixtures. They never
accept a source business DSN or copy a teacher's class data into model context.
"""
import asyncio
import json
import hashlib
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from contextlib import asynccontextmanager
from dataclasses import replace
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import text

from class_os.application.agent import AgentRequest, DraftKind, Mode, AgentRejected
from class_os.domain.roster import CreateStudent
from class_os.domain.activity import CreateTask, ChangeTask
from class_os.infrastructure.agent import PydanticAgentRuntime
from test_agent_api_protocol import protocol_reply, MODEL, KEY
from class_os.infrastructure import provider_evaluation as evaluation
from test_activity_gateway import seed, submit
from test_roster_gateway import roster
from test_identity import identity


@pytest.mark.parametrize("values", [("NaN", 1, 10), (1, "Infinity", 10), (0, 1, 10), (1, 1, 11), (-1, 1, 10)])
def test_budget_rejects_unknown_or_unapproved_prices(values):
    with pytest.raises(evaluation.EvalBlocked):
        evaluation.Budget(*values)


def test_dataset_and_budget_are_closed_and_bounded():
    assert len(evaluation.CASES) == len({case.id for case in evaluation.CASES}) == 12
    assert len(evaluation.DATASET_HASH) == 64
    budget = evaluation.Budget("1", "2")
    budget.preflight()
    budget.reserve()
    assert budget.reserved > 0
    with pytest.raises(evaluation.EvalBlocked):
        evaluation.Budget("1000", "1000").preflight()
    with pytest.raises(evaluation.EvalBlocked):
        budget.preflight(0)
    # 146 used to omit the three extra PE-03 runs (12 requests).
    threshold = evaluation.Budget("2.2", "2.2")
    threshold.preflight(146)
    with pytest.raises(evaluation.EvalBlocked):
        threshold.preflight()


def test_budget_keeps_failed_reservation_and_never_admits_over_limit():
    budget = evaluation.Budget("1", "1", ".04")
    budget.reserve()
    first = budget.reserved
    with pytest.raises(evaluation.EvalBlocked):
        budget.reserve()
    assert budget.reserved == first and budget.reserved <= budget.limit


@pytest.mark.db
@pytest.mark.parametrize("case", evaluation.CASES, ids=lambda case: case.id)
async def test_provider_synthetic_scenario(roster, case):
    gateway, query, _, credentials, _, owner, _ = roster
    classroom, student, record = seed(roster)
    submit(gateway, credentials, record)
    submit(gateway, credentials, CreateStudent(uuid4(), classroom.class_id, classroom.term_id, 1, student.name))
    direct = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成学生跟进", None, student.student_id, None)
    waiting = CreateTask("task.create", uuid4(), classroom.class_id, classroom.term_id, "合成班级等待", None, None, None)
    submit(gateway, credentials, direct)
    submit(gateway, credentials, waiting)
    submit(gateway, credentials, ChangeTask("task.update", waiting.task_id, classroom.class_id, classroom.term_id, 1, "waiting"))
    for repetition in range(3):
        metrics = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "usage_known": True}
        live = evaluation.LIVE_SOURCE
        runtime = PydanticAgentRuntime(query)
        if live:
            @asynccontextmanager
            async def model_context(_credentials, request):
                async with live["controller"].context(live["credentials"], request) as model:
                    yield evaluation.MeteredModel(model, metrics, live["budget"])
            runtime.model_context = model_context
            runtime.provider_state = lambda _: "configured-api"
        if case.scope in ("timeout", "cancel"):
            # Explicit injected boundary failure; not measured supplier quality.
            from pydantic_ai.models.function import FunctionModel
            entered = asyncio.Event()
            async def stalled(messages, info):
                entered.set()
                await asyncio.sleep(30)
            runtime = PydanticAgentRuntime(query, model_factory=lambda _: FunctionModel(stalled), timeout=.1 if case.scope == "timeout" else 10)
        options = {"student_id": student.student_id} if case.scope == "student" else {}
        conversation = runtime.conversation(credentials, **options)
        request = AgentRequest(conversation.conversation_id, case.text, Mode(case.mode), DraftKind(case.kind))
        submit_count = 0
        with owner.transaction(read_only=True) as connection:
            before = tuple(connection.execute(text(f"SELECT count(*) FROM class_os.{table}")).scalar_one() for table in ("student", "record_revision", "manual_task", "command_receipt"))
        if case.scope == "unauthorized":
            with pytest.raises(Exception) as rejected:
                await evaluation.collect(runtime, (*credentials[:3], uuid4()), request)
            assert type(rejected.value).__name__ in ("IdentityDenied", "AgentRejected")
            outcome, duration = {"passed": True, "quality": "pre-provider-boundary", "tools": [], "reasons": []}, 0
        elif case.scope == "cancel":
            running = asyncio.create_task(evaluation.collect(runtime, credentials, request))
            await asyncio.wait_for(entered.wait(), 3)
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
            assert not conversation.history and runtime.active == 0
            outcome, duration = {"passed": True, "quality": "injected-boundary", "tools": [], "reasons": []}, 0
        else:
            expected = query.work_snapshot(*credentials, classroom.class_id, classroom.term_id, **options)
            events, duration = await evaluation.collect(runtime, credentials, request)
            if case.scope == "timeout":
                assert events[-1].type == "run.failed" and not conversation.history and runtime.active == 0
                outcome = {"passed": True, "quality": "injected-boundary", "tools": [], "reasons": []}
            else:
                outcome = evaluation.check_result(case, events, {"open_tasks": expected.open_tasks, "waiting_tasks": expected.waiting_tasks, "record_count": expected.record_count}, real_provider=bool(live), source_hash=expected.source_hash)
                for event in events:
                    if event.type == "message.delta":
                        for source in event.payload.get("source_refs", []):
                            with owner.transaction(read_only=True) as connection:
                                audit = connection.execute(text("SELECT class_id,term_id,resource_id,action,outcome FROM class_os.business_audit WHERE event_id=:id"), {"id": source["id"]}).one()
                            assert tuple(audit) == (classroom.class_id, classroom.term_id, student.student_id if options else classroom.class_id, "activity.today", "allowed")
                if case.scope == "fresh":
                    submit(gateway, credentials, replace(record, record_id=uuid4()))
                    changed = query.work_snapshot(*credentials, classroom.class_id, classroom.term_id)
                    next_events, next_duration = await evaluation.collect(runtime, credentials, request)
                    duration += next_duration
                    assert changed.record_count == expected.record_count + 1
                    second = evaluation.check_result(case, next_events, {"open_tasks": changed.open_tasks, "waiting_tasks": changed.waiting_tasks, "record_count": changed.record_count}, real_provider=bool(live), source_hash=changed.source_hash)
                    outcome["passed"] = outcome["passed"] and second["passed"]
                    outcome["reasons"] += second["reasons"]
                    submit_count = 1
                else:
                    submit_count = 0
                if case.kind == "record-note":
                    drafts = [event.payload["draft"] for event in events if event.type == "draft.available"]
                    assert drafts and drafts[0]["note_quote"] in case.text
                    candidate = drafts[0]
                    assert case.text[candidate["source_start"]:candidate["source_end"]] == candidate["note_quote"]
                    assert candidate["source_hash"] == hashlib.sha256(case.text.encode()).hexdigest()
                    assert "student_id" not in candidate and "occurred_at" not in candidate
            if case.scope != "fresh":
                submit_count = 0
        with owner.transaction(read_only=True) as connection:
            after = tuple(connection.execute(text(f"SELECT count(*) FROM class_os.{table}")).scalar_one() for table in ("student", "record_revision", "manual_task", "command_receipt"))
        assert after == (before[0], before[1] + submit_count, before[2], before[3] + submit_count)
        evaluation.RESULTS.append({"case": case.id, "repetition": repetition + 1, "provider": "configured-api" if live and case.scope not in ("timeout", "cancel", "unauthorized") else "offline-boundary", "duration_ms": duration,
                                   "input_tokens": metrics["input_tokens"] if live and metrics["usage_known"] and metrics["requests"] else None,
                                   "output_tokens": metrics["output_tokens"] if live and metrics["usage_known"] and metrics["requests"] else None,
                                   "requests": metrics["requests"], "resolved_models": sorted(metrics.get("resolved_models", [])),
                                   "review_text": [event.payload["text"][:4000] for event in events if event.type == "message.delta"] if live and case.scope not in ("unauthorized", "cancel") else [], **outcome})
        assert outcome["passed"], outcome["reasons"]


def test_operator_without_explicit_configuration_blocks_before_credentials_or_network():
    completed = subprocess.run([sys.executable, "evaluate_provider.py"], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
    assert completed.returncode == 2
    result = json.loads(completed.stdout)
    assert result["status"] == "blocked" and result["paid_requests"] == 0
    assert "Owner password" not in completed.stdout and not completed.stderr


def test_empty_metrics_are_unknown_not_fake_zero_or_improvement():
    report = evaluation.summarize([])
    assert report["p95_ms"] is None and report["input_tokens"] is None
    report = evaluation.summarize([{"provider": "offline-boundary", "duration_ms": 1}])
    assert report["real_provider_runs"] == 0


def baseline_report():
    rows = [{"case": case.id, "repetition": repetition, "passed": True,
             "provider": "offline-boundary" if case.scope in ("timeout", "cancel", "unauthorized") else "configured-api",
             "duration_ms": 10, "input_tokens": None, "output_tokens": None,
             "requests": 0 if case.scope in ("timeout", "cancel", "unauthorized") else 1,
             "resolved_models": [] if case.scope in ("timeout", "cancel", "unauthorized") else ["synthetic-test-model"]}
            for case in evaluation.CASES for repetition in range(1, 4)]
    return {**{key: "a" * 64 for key in ("dataset_hash", "configuration_hash", "lock_sha256", "agent_source_sha256", "tool_contract_sha256")},
            "schema_version": "classmatter.synthetic-provider-eval.v1", "status": "needs-human-review",
            "formal_release_evidence": False, "resolved_models": ["synthetic-test-model"],
            "environment": evaluation.environment_fingerprint(), "model_settings": dict(evaluation.MODEL_SETTINGS),
            "results": rows, "summary": evaluation.summarize(rows)}


def test_regression_comparison_does_not_compare_other_models_or_invent_missing_usage():
    before = baseline_report()
    after = deepcopy(before)
    after["results"][0].update(duration_ms=30, passed=False)
    after["status"] = "failed-or-incomplete"
    after["results"][1]["duration_ms"] = 30
    after["summary"] = evaluation.summarize(after["results"])
    comparison = evaluation.compare_reports(after, before)
    assert comparison["metric_deltas"]["input_tokens"] is None
    assert set(comparison["alerts"]) == {"p95_ms_increased_over_20pct", "case_pass_regression"}
    assert evaluation.compare_reports({**after, "configuration_hash": "b" * 64}, before)["status"] == "incomparable-configuration"


@pytest.mark.parametrize("fault", ["missing", "duplicate", "nonfinite", "negative", "boolean-token", "summary", "not-object", "status", "offline", "environment", "model_settings", "models", "requests", "offline-usage", "unpaired-usage", "false-success", "no-model"])
def test_baseline_validation_rejects_invalid_reports(fault):
    report = baseline_report()
    if fault == "missing":
        report["results"].pop()
    elif fault == "duplicate":
        report["results"][1] = dict(report["results"][0])
    elif fault == "nonfinite":
        report["results"][0]["duration_ms"] = float("nan")
    elif fault == "negative":
        report["results"][0]["input_tokens"] = -1
    elif fault == "boolean-token":
        report["results"][0]["input_tokens"] = True
    elif fault == "summary":
        report["summary"]["p95_ms"] = "not-a-number"
    elif fault == "not-object":
        report = []
    elif fault == "status":
        report["status"] = "unverified"
    elif fault == "offline":
        report["results"][0]["provider"] = "offline-boundary"
    elif fault in ("environment", "model_settings"):
        report.pop(fault)
    elif fault == "models":
        report["resolved_models"] = ["forged-model"]
    elif fault == "requests":
        report["results"][0]["requests"] = True
    elif fault == "offline-usage":
        report["results"][-1]["input_tokens"] = 5
    elif fault == "unpaired-usage":
        report["results"][0]["output_tokens"] = 5
    elif fault == "false-success":
        report["results"][0]["passed"] = False
    else:
        report["results"][0]["resolved_models"] = []
    with pytest.raises(evaluation.EvalBlocked):
        evaluation.validate_report(report)
    assert evaluation.compare_reports(baseline_report(), report)["status"] == "incomparable-invalid-or-incomplete-report"


def test_comparison_rejects_environment_and_usage_cohort_changes():
    before = baseline_report()
    assert evaluation.validate_report(before) is before
    assert evaluation.compare_reports(before, before)["status"] == "comparable"
    for key in ("environment", "model_settings"):
        other = deepcopy(before)
        other.pop(key)
        assert evaluation.compare_reports(other, before)["status"] == "incomparable-invalid-or-incomplete-report"
        other[key] = {**before[key], "release": "different"} if key == "environment" else {**before[key], "max_tokens": 512}
        assert evaluation.compare_reports(other, before)["status"] == "incomparable-configuration"
    other = deepcopy(before)
    other["results"][0]["input_tokens"] = 20
    other["results"][0]["output_tokens"] = 5
    other["summary"] = evaluation.summarize(other["results"])
    assert evaluation.compare_reports(other, before)["status"] == "incomparable-measurement-coverage"


def test_equal_total_passes_cannot_hide_a_new_case_regression():
    before = baseline_report()
    before["status"] = "failed-or-incomplete"
    before["results"][0]["passed"] = False
    after = deepcopy(before)
    after["results"][0]["passed"] = True
    after["results"][1]["passed"] = False
    result = evaluation.compare_reports(after, before)
    assert result["previous_passed"] == result["current_passed"] == 35
    assert result["alerts"] == ["case_pass_regression"]
    assert result["newly_failed_cases"] == [{"case": "PE-01", "repetition": 2}]


def test_source_hash_and_tool_oracle_rejects_wrong_scope_proof_and_unknown_tool():
    events = [SimpleNamespace(type="tool.started", payload={"tool": "commands_commit"}),
              SimpleNamespace(type="message.delta", payload={"text": "{}", "source_refs": [{"id": str(uuid4()), "entity": "query_receipt", "version": 1, "projection_hash": "a" * 64}]}),
              SimpleNamespace(type="run.completed", payload={})]
    result = evaluation.check_result(evaluation.CASES[0], events, {}, source_hash="b" * 64)
    assert set(result["reasons"]) == {"unauthorized_tool", "invalid_source"}


@pytest.mark.db
async def test_metering_wraps_real_sdk_protocol_without_network_or_business_writes(roster):
    import httpx
    from openai import AsyncOpenAI
    from class_os.domain.model_configuration import ModelConfiguration, Protocol
    from class_os.infrastructure.model_provider import model_for_configuration
    _, query, _, credentials, _, _, _ = roster
    seed(roster)
    metrics = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "usage_known": True}
    budget = evaluation.Budget("1", "1")
    calls = []
    def reply(request):
        calls.append(request)
        return httpx.Response(200, json=protocol_reply("chat-completions", json.loads(request.content), len(calls)))
    @asynccontextmanager
    async def context(_credentials, _request):
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply), trust_env=False) as http:
            async with AsyncOpenAI(api_key=KEY, base_url="https://provider.example.invalid/v1", max_retries=0, organization="", project="", http_client=http) as client:
                model = model_for_configuration(ModelConfiguration(Protocol.CHAT, MODEL, "https://provider.example.invalid/v1"), client)
                yield evaluation.MeteredModel(model, metrics, budget)
    runtime = PydanticAgentRuntime(query, model_context=context, provider_label="synthetic-api-protocol")
    conversation = runtime.conversation(credentials)
    events, _ = await evaluation.collect(runtime, credentials, AgentRequest(conversation.conversation_id, "合成协议计量", Mode.READ))
    assert events[-1].type == "run.completed"
    assert metrics["requests"] == len(calls) == 2
    assert (metrics["input_tokens"], metrics["output_tokens"], metrics["usage_known"]) == (20, 10, True)
    assert budget.reserved == budget.cost() * 2
