"""D1 domain evidence, NOT a durable store or real Provider quality test."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from class_os.domain.durable_conversation import (
    ConversationRun, ConversationScope, SendIntent, VisibleMessage,
)


NOW = datetime(2026, 10, 24, 0, tzinfo=timezone.utc)


def intent():
    return SendIntent(ConversationScope(uuid4(), uuid4(), uuid4(), uuid4()),
                      uuid4(), uuid4(), "合成班务查询", "read")


def running():
    return ConversationRun(uuid4()).start(1, uuid4(), NOW, NOW + timedelta(minutes=1))


def test_exact_replay_is_not_changed_payload_or_a_new_request():
    item = intent()
    assert len(item.request_hash) == 64 and item.is_replay_of(replace(item))
    assert not item.is_replay_of(replace(item, client_request_id=uuid4()))
    for change in ({"text": item.text + " "}, {"mode": "draft"}, {"mode": "chat"}, {"draft_kind": "record-note"}):
        with pytest.raises(ValueError, match="key conflict"):
            replace(item, **change).is_replay_of(item)
    for field in ("workspace_id", "owner_id", "class_id", "term_id", "student_id"):
        changed = replace(item, scope=replace(item.scope, **{field: uuid4()}))
        assert changed.request_hash != item.request_hash and not changed.is_replay_of(item)
    assert replace(item, thread_id=uuid4()).request_hash != item.request_hash
    with pytest.raises(FrozenInstanceError):
        item.text = "不能原地覆盖"


@pytest.mark.parametrize("text", ["", "  ", "x" * 2001, "x" * 8001, "合" * 5334, "\x00", "\ud800", "\u202e"])
def test_visible_input_rejects_empty_oversized_or_hidden_control_text(text):
    with pytest.raises(ValueError):
        replace(intent(), text=text)


@pytest.mark.parametrize("role,origin", [("assistant", "fact"), ("tool", "user-original"),
    ("system", "assistant-unverified"), ("user", "assistant-unverified")])
def test_visible_history_cannot_be_tool_system_or_verified_fact(role, origin):
    with pytest.raises(ValueError):
        VisibleMessage(role, origin, "合成文本")


def test_visible_history_preserves_original_text_without_claiming_current_fact():
    assert VisibleMessage("user", "user-original", "原文\n\t ").text == "原文\n\t "
    assert VisibleMessage("assistant", "assistant-unverified", "合成草稿").origin == "assistant-unverified"
    for change in ({"mode": "write"}, {"draft_kind": "sql"}, {"thread_id": "not-uuid"}, {"scope": {}}):
        with pytest.raises(ValueError):
            replace(intent(), **change)


def test_queued_cancellation_never_dispatches_or_claims_a_provider_result():
    item = ConversationRun(uuid4()).request_cancel(1, NOW)
    assert item.state == "cancelled" and item.started_at is None and item.generation is None
    with pytest.raises(ValueError):
        item.start(item.version, uuid4(), NOW, NOW + timedelta(minutes=1))


def test_cancel_request_is_not_confirmation_and_late_answer_is_not_success():
    item = running().request_cancel(2, NOW + timedelta(seconds=1))
    assert item.state == "cancel_requested" and item.ended_at is None
    assert item.request_cancel(3, NOW + timedelta(seconds=2)) is item
    with pytest.raises(ValueError):
        item.finish(3, item.generation, "completed", NOW + timedelta(seconds=2))
    confirmed = item.finish(3, item.generation, "cancelled", NOW + timedelta(seconds=2))
    assert confirmed.state == "cancelled" and confirmed.version == 4


def test_reconstructed_terminal_rows_enforce_lease_and_cancellation_chronology():
    item = running()
    for state in ("completed", "failed", "cancelled", "unknown"):
        for at in (item.lease_until, item.lease_until + timedelta(seconds=1), NOW - timedelta(seconds=1)):
            with pytest.raises(ValueError):
                replace(item, state=state, ended_at=at)
    with pytest.raises(ValueError):
        replace(item, state="interrupted", ended_at=item.lease_until - timedelta(seconds=1))
    assert replace(item, state="interrupted", ended_at=item.lease_until).state == "interrupted"
    requested = item.request_cancel(2, NOW + timedelta(seconds=20))
    for state in ("failed", "cancelled", "unknown"):
        with pytest.raises(ValueError, match="chronology"):
            requested.finish(3, requested.generation, state, NOW + timedelta(seconds=10))
    with pytest.raises(ValueError):
        requested.request_cancel(3, NOW + timedelta(seconds=10))
    for change in ({"cancel_requested_at": None}, {"cancel_requested_at": item.lease_until},
                   {"cancel_requested_at": NOW - timedelta(seconds=1)}, {"state": "running"}):
        with pytest.raises(ValueError):
            replace(requested, **change)


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled", "unknown"])
def test_terminal_is_immutable_and_does_not_allow_automatic_retry(state):
    item = running()
    done = item.finish(2, item.generation, state, NOW + timedelta(seconds=3))
    assert done.state == state and done.ended_at is not None
    for operation in (lambda: done.finish(3, done.generation, state, NOW),
                      lambda: done.start(3, uuid4(), NOW, NOW + timedelta(seconds=30)),
                      lambda: done.request_cancel(3, NOW), lambda: done.expire(3, NOW + timedelta(minutes=2))):
        with pytest.raises(ValueError):
            operation()


def test_expiry_fences_old_completion_at_exact_boundary_without_auto_retry():
    item = running()
    with pytest.raises(ValueError):
        item.expire(2, item.lease_until - timedelta(microseconds=1))
    for state in (item, item.request_cancel(2, NOW)):
        expired = state.expire(state.version, state.lease_until)
        assert expired.state == "interrupted" and expired.generation == item.generation
        with pytest.raises(ValueError):
            state.finish(state.version, state.generation, "completed", state.lease_until)
        with pytest.raises(ValueError):
            expired.finish(expired.version, item.generation, "completed", NOW)


@pytest.mark.parametrize("expected,generation,state,at", [
    (1, None, "completed", NOW), (True, None, "completed", NOW),
    (2, "wrong", "completed", NOW), (2, None, "queued", NOW),
    (2, None, "completed", NOW - timedelta(seconds=1)),
])
def test_version_generation_closed_state_and_clock_are_checked(expected, generation, state, at):
    item = running()
    with pytest.raises(ValueError):
        item.finish(expected, generation if generation is not None else item.generation, state, at)


@pytest.mark.parametrize("change", [{"state": "completed"}, {"state": "other"}, {"version": True},
    {"generation": uuid4()}, {"ended_at": NOW}])
def test_invalid_persisted_run_rows_are_rejected(change):
    with pytest.raises(ValueError):
        replace(ConversationRun(uuid4()), **change)


@pytest.mark.parametrize("lease", [NOW, NOW - timedelta(seconds=1), NOW + timedelta(minutes=6)])
def test_leases_are_positive_bounded_and_timestamp_is_aware(lease):
    with pytest.raises(ValueError):
        ConversationRun(uuid4()).start(1, uuid4(), NOW, lease)
    with pytest.raises(ValueError):
        ConversationRun(uuid4()).start(1, uuid4(), NOW.replace(tzinfo=None), NOW + timedelta(minutes=1))
