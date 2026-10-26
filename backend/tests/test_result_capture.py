"""Private SDK correlation syntax; not a substitute for actual QG/SQL tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from class_os.application.conversation_interaction import ConversationInteractionQuery
from class_os.application.result_capture import CapturedResult, ResultCapture
from class_os.application.roster import CommandRejected
from class_os.domain.conversation_results import QuerySource, ProducedResult
from class_os.domain.conversation_worker import ClaimedRun
from class_os.domain.durable_conversation import ConversationScope, SendIntent, ConversationRun
from class_os.domain.query_snapshot import WorkSnapshot
from class_os.domain.activity import CreateTask


def setup(mode="read"):
    scope = ConversationScope(uuid4(), uuid4(), uuid4(), uuid4())
    now = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    intent = SendIntent(scope, uuid4(), uuid4(), "synthetic input", mode)
    run = ConversationRun(uuid4()).start(1, uuid4(), now, now+timedelta(minutes=1))
    ticket = ClaimedRun(scope, uuid4(), intent, run)
    credentials = ("synthetic-token", "synthetic-client", "synthetic-csrf", scope.workspace_id)
    query = ConversationInteractionQuery(object(), object())
    capture = ResultCapture(ticket, credentials, query)
    sdk = uuid4()
    capture.begin(sdk, credentials)
    projection = WorkSnapshot(scope.class_id, scope.term_id, 1, now, 0, 0, 0, "a" * 64, audit_id=uuid4())
    return capture, sdk, credentials, query, projection


def test_same_clock_historical_audit_cannot_replace_observed_current_read():
    capture, sdk, credentials, query, projection = setup()
    old = replace(projection, audit_id=uuid4())  # same scope/hash/as_of, distinct original query receipt
    forged = QuerySource.from_tool(capture.ticket.scope, old.tool_payload()["source_refs"][0])
    capture.observe_read(sdk, credentials, projection)
    capture.completed(sdk, credentials, "synthetic response")
    with pytest.raises(CommandRejected):
        capture.seal(sdk, credentials, ProducedResult("synthetic response", (forged,)))
    result = capture.seal(sdk, credentials, ProducedResult("synthetic response", capture.sources))
    assert result.verify(query.store, query.identity, credentials, capture.ticket).sources == capture.sources
    with pytest.raises(CommandRejected):
        result.verify(object(), query.identity, credentials, capture.ticket)
    with pytest.raises(CommandRejected):
        result.verify(query.store, query.identity, ("different-session", *credentials[1:]), capture.ticket)
    capture.close()
    with pytest.raises(CommandRejected):
        result.verify(query.store, query.identity, credentials, capture.ticket)


def test_no_sdk_completion_or_unobserved_sources_cannot_mint_outcome():
    capture, sdk, credentials, _, projection = setup()
    with pytest.raises(CommandRejected):
        capture.seal(sdk, credentials, ProducedResult("synthetic"))
    with pytest.raises(CommandRejected):
        capture.observe_read(uuid4(), credentials, projection)
    with pytest.raises(CommandRejected):
        CapturedResult(capture, ProducedResult("synthetic"))
    with pytest.raises(ValueError):
        capture.completed(sdk, credentials, "synthetic read without query")


def test_actual_task_candidate_is_scoped_and_plaintext_is_not_retained_by_collector():
    capture, sdk, credentials, query, _ = setup("draft")
    scope = capture.ticket.scope
    task = CreateTask("task.create", uuid4(), scope.class_id, scope.term_id, "synthetic draft")
    capture.observe_draft(sdk, credentials, task)
    capture.completed(sdk, credentials, "synthetic response")
    with pytest.raises(CommandRejected):
        capture.seal(sdk, credentials, ProducedResult("synthetic changed response", draft=task))
    with pytest.raises(CommandRejected):
        capture.seal(sdk, credentials, ProducedResult("synthetic response", draft=replace(task, title="synthetic changed title")))
    result = capture.seal(sdk, credentials, ProducedResult("synthetic response", draft=task))
    assert result.verify(query.store, query.identity, credentials, capture.ticket).draft == task
    assert not hasattr(capture, "text") and capture.output_hash != "synthetic response"
