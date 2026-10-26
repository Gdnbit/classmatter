"""Fixed output syntax/intent boundaries, not database or Provider evidence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from class_os.domain.activity import CreateTask
from class_os.domain.conversation_results import (QuerySource, ProducedResult, FinishResult, decode_finish_result,
                                                RESULT_COLUMNS, RESULT_ENTITY_KEYS)
from class_os.domain.conversation_worker import decode_run
from class_os.domain.durable_conversation import ConversationScope, SendIntent
from class_os.domain.roster import decode
from class_os.domain.target_import import ENTITY_KEYS
from class_os.domain.conversation_exit_v3 import CONVERSATION_COLUMNS
from class_os.domain.conversation_result_integrity import validate_result_rows
from class_os.domain.exit_package import checksum


def fixture():
    scope = ConversationScope(uuid4(), uuid4(), uuid4(), uuid4())
    now = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    source = QuerySource(uuid4(), scope.workspace_id, scope.owner_id, uuid4(), "a" * 64, now)
    intent = SendIntent(scope, uuid4(), uuid4(), "synthetic input", "read")
    return scope, source, intent


def test_sources_are_closed_canonical_and_do_not_widen_legacy_registries():
    scope, source, _ = fixture()
    assert QuerySource.from_tool(scope, source.tool_ref(), source_id=source.source_id) == source
    assert set(RESULT_COLUMNS) == set(RESULT_ENTITY_KEYS)
    assert not set(RESULT_COLUMNS) & set(ENTITY_KEYS)
    assert not set(RESULT_COLUMNS) & set(CONVERSATION_COLUMNS)
    for extra in ({"sql": "synthetic"}, {"version": True}, {"entity": "student"}, {"as_of": source.as_of.replace(tzinfo=None).isoformat()}):
        with pytest.raises(ValueError):
            QuerySource.from_tool(scope, {**source.tool_ref(), **extra})


def test_mode_scope_and_task_candidate_remain_exact_and_uncommitted():
    scope, source, intent = fixture()
    answer = ProducedResult("synthetic answer", (source,))
    answer.validate_intent(intent)
    task = CreateTask("task.create", uuid4(), scope.class_id, scope.term_id, "synthetic task")
    candidate = ProducedResult("synthetic uncommitted draft", draft=task)
    candidate.validate_intent(replace(intent, mode="draft"))
    ProducedResult("synthetic chat").validate_intent(replace(intent, mode="chat"))
    assert "approved" not in str(candidate.canonical()) and "committed" not in candidate.canonical()
    for bad in (ProducedResult("synthetic"), candidate, ProducedResult("synthetic", (replace(source, source_owner_id=uuid4()),))):
        with pytest.raises(ValueError):
            bad.validate_intent(intent)
    for changed in (replace(intent, mode="chat"), replace(intent, mode="draft"), replace(intent, mode="draft", draft_kind="record-note")):
        with pytest.raises(ValueError):
            answer.validate_intent(changed)
    with pytest.raises(ValueError):
        ProducedResult("synthetic", draft=replace(task, class_id=uuid4())).validate_intent(replace(intent, mode="draft"))
    with pytest.raises(ValueError):
        ProducedResult("synthetic", draft=replace(task, due_at=source.as_of + timedelta(days=1)))
    with pytest.raises(ValueError):
        ProducedResult("synthetic chat").validate_intent(replace(intent, mode="chat", draft_kind="record-note"))


def test_output_limit_duplicates_hash_and_metadata_no_plaintext_copy():
    _, source, intent = fixture()
    answer = ProducedResult("synthetic private output", (source,))
    changed = ProducedResult("synthetic changed output", (source,))
    assert answer.result_hash != changed.result_hash
    command = FinishResult(intent.thread_id, intent.scope.class_id, intent.scope.term_id, uuid4(), 2, uuid4(), answer.result_hash)
    payload = command.canonical()
    assert decode_finish_result(payload) == command and "synthetic private" not in str(payload)
    for parser in (decode, decode_run):
        with pytest.raises(ValueError):
            parser(payload)
    with pytest.raises(ValueError):
        decode_finish_result({**payload, "approval": "synthetic"})
    for sources in ((source, source), (source, replace(source, source_id=uuid4())), [source]):
        with pytest.raises(ValueError):
            ProducedResult("synthetic", sources)
    with pytest.raises(ValueError):
        ProducedResult("x" * 4001)
    with pytest.raises(ValueError):
        replace(command, input_tokens=True)
    assert "synthetic private output" not in repr(answer)


def rows_fixture(mode="read"):
    scope, source, intent = fixture()
    at = source.as_of.isoformat()
    key = {"workspace_id": str(scope.workspace_id), "thread_id": str(intent.thread_id), "turn_id": str(uuid4()), "message_id": str(uuid4())}
    result = {"conversation_thread": [{**key, "class_id": str(scope.class_id), "term_id": str(scope.term_id), "student_id": None}],
        "conversation_turn": [{**key, "mode": mode, "draft_kind": "task"}],
        "conversation_run": [{**key, "state": "completed", "started_at": at, "ended_at": at}],
        "conversation_message": [{**key, "role": "assistant", "origin": "assistant-unverified", "visibility": "visible", "body": "synthetic reply", "created_at": at}],
        "conversation_query_source": [], "conversation_task_draft": []}
    if mode == "read":
        result["conversation_query_source"] = [{**key, **source.canonical(), "message_role": "assistant", "ordinal": 1, "created_at": at}]
    else:
        result["conversation_task_draft"] = [{**key, "draft_id": str(uuid4()), "message_role": "assistant", "title": "synthetic candidate",
            "title_hash": checksum("synthetic candidate"), "visibility": "visible", "created_at": at}]
    from class_os.domain.conversation_exit_v6 import result_value
    value = result_value(result["conversation_thread"][0], result["conversation_message"][0], {
        "sources": result["conversation_query_source"], "draft": next(iter(result["conversation_task_draft"]), None)})
    result["conversation_result_receipt"] = [{**key, "message_role": "assistant", "protocol": "fixed-result", "text_hash": checksum(value.text), "result_hash": value.result_hash, "created_at": at, "recorded_at": at}]
    return scope, source, result


@pytest.mark.parametrize("mode", ["read", "draft"])
def test_fixed_result_relations_and_clear_without_hidden_title_copy(mode):
    scope, source, rows = rows_fixture(mode)
    assert len(validate_result_rows(rows, str(scope.workspace_id), source.as_of.isoformat())) == 1
    if mode == "draft":
        rows["conversation_message"][0].update(body=None, visibility="restricted")
        rows["conversation_task_draft"][0].update(title=None, visibility="restricted")
        assert validate_result_rows(rows, str(scope.workspace_id), source.as_of.isoformat())


@pytest.mark.parametrize("fault", ["message", "role", "state", "time", "ordinal", "duplicate", "extra"])
def test_result_relations_reject_foreign_or_out_of_run_sources(fault):
    scope, source, rows = rows_fixture()
    row = rows["conversation_query_source"][0]
    if fault == "message":
        row["message_id"] = str(uuid4())
    elif fault == "role":
        row["message_role"] = "user"
    elif fault == "state":
        rows["conversation_run"][0]["state"] = "unknown"
    elif fault == "time":
        row["as_of"] = (source.as_of - timedelta(seconds=1)).isoformat()
    elif fault == "ordinal":
        row["ordinal"] = True
    elif fault == "duplicate":
        rows["conversation_query_source"].append({**row, "source_id": str(uuid4()), "ordinal": 2})
    else:
        row["approval"] = "synthetic"
    with pytest.raises(ValueError):
        validate_result_rows(rows, str(scope.workspace_id), source.as_of.isoformat())
