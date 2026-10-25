"""Closed metadata and no authority/SDK state implied by a domain value."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from class_os.domain.conversation_worker import ClaimRun, FinishRun, CancelRun, ReconcileRun, decode_run, ClaimedRun
from class_os.domain.conversation_interaction import decode_interaction
from class_os.domain.durable_conversation import ConversationRun, ConversationScope, SendIntent
from class_os.domain.roster import decode


def values():
    scope = ConversationScope(uuid4(), uuid4(), uuid4(), uuid4())
    intent = SendIntent(scope, uuid4(), uuid4(), "合成人工输入", "chat")
    at = datetime(2026, 10, 8, tzinfo=timezone.utc)
    run = ConversationRun(uuid4()).start(1, uuid4(), at, at + timedelta(minutes=1))
    common = (intent.thread_id, scope.class_id, scope.term_id, run.run_id, 1)
    return intent, run, common


def test_closed_run_metadata_is_not_r1_or_human_input_command():
    intent, run, common = values()
    commands = (ClaimRun(*common, run.generation, run.lease_until, intent.request_hash),
        FinishRun(*common[:-1], 2, run.generation, "completed", "a" * 64), CancelRun(*common), ReconcileRun(*common))
    for command in commands:
        assert decode_run(command.canonical()) == command
        assert intent.text not in str(command.canonical())
        for parse in (decode, decode_interaction):
            with pytest.raises(ValueError):
                parse(command.canonical())
        with pytest.raises(ValueError):
            decode_run({**command.canonical(), "output": "合成不允许日志正文"})


@pytest.mark.parametrize("bad", [True, -1, 2147483648, "1"])
def test_metrics_are_bounded_not_coerced(bad):
    _, run, common = values()
    with pytest.raises(ValueError):
        FinishRun(*common, run.generation, "completed", "a" * 64, duration_ms=bad)


def test_terminal_metadata_and_private_claim_do_not_restore_authority():
    intent, run, common = values()
    assert ClaimedRun(intent.scope, uuid4(), intent, run).run.generation == run.generation
    with pytest.raises(ValueError):
        ClaimedRun(intent.scope, uuid4(), intent, ConversationRun(run.run_id))
    for state, digest in (("failed", "a" * 64), ("completed", None), ("running", None)):
        with pytest.raises(ValueError):
            FinishRun(*common, run.generation, state, digest)
    with pytest.raises(ValueError):
        ClaimRun(*common, run.generation, run.lease_until.replace(tzinfo=None), intent.request_hash)
