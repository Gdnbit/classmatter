"""Fixed human metadata rules. No persistence, dispatch or authorization claim."""
from dataclasses import replace
import json
from uuid import uuid4

import pytest

from class_os.domain.conversation_interaction import (CreateConversation, RenameConversation, ArchiveConversation,
    EnqueueConversation, decode_interaction)
from class_os.domain.durable_conversation import ConversationScope, SendIntent
from class_os.domain.roster import decode
from class_os.domain.exit_package import checksum


def intent():
    scope = ConversationScope(uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
    return SendIntent(scope, uuid4(), uuid4(), "合成输入原文，不应进入命令日志", "chat")


def test_fixed_interactions_are_not_r1_commands_or_arbitrary_schema():
    sent = intent()
    commands = (CreateConversation(sent.thread_id, sent.scope.class_id, sent.scope.term_id, checksum("合成会话")),
        RenameConversation(sent.thread_id, sent.scope.class_id, sent.scope.term_id, 1, checksum("合成改名")),
        ArchiveConversation(sent.thread_id, sent.scope.class_id, sent.scope.term_id, 1), EnqueueConversation.from_intent(sent))
    for command in commands:
        assert decode_interaction(command.canonical()) == command
        with pytest.raises(ValueError):
            decode(command.canonical())
        with pytest.raises(ValueError):
            decode_interaction({**command.canonical(), "text": sent.text})
        with pytest.raises(ValueError):
            decode_interaction({**command.canonical(), "command": "conversation.arbitrary"})


def test_queued_proposal_is_metadata_only_and_matches_complete_human_intent():
    sent = intent()
    command = EnqueueConversation.from_intent(sent)
    assert sent.text not in json.dumps(command.canonical(), ensure_ascii=False)
    assert "text" not in command.canonical() and "body" not in command.canonical()
    assert command.matches(sent)
    for changed in (replace(sent, text=sent.text + "!"), replace(sent, mode="read"),
                    replace(sent, client_request_id=uuid4()), replace(sent, thread_id=uuid4()),
                    replace(sent, scope=replace(sent.scope, owner_id=uuid4())),
                    replace(sent, scope=replace(sent.scope, workspace_id=uuid4())),
                    replace(sent, scope=replace(sent.scope, student_id=None))):
        assert not command.matches(changed)


@pytest.mark.parametrize("value", [True, 0, -1, 2147483647, "1"])
def test_invalid_expected_version_is_not_a_mutation(value):
    sent = intent()
    with pytest.raises(ValueError):
        ArchiveConversation(sent.thread_id, sent.scope.class_id, sent.scope.term_id, value)


@pytest.mark.parametrize("title", ["", " ", "x" * 81, "合成\n标题", "合成\u200b标题"])
def test_raw_title_is_not_a_metadata_hash(title):
    sent = intent()
    with pytest.raises(ValueError):
        CreateConversation(sent.thread_id, sent.scope.class_id, sent.scope.term_id, title)


def test_unsupported_runtime_mode_is_not_saved_first():
    sent = intent()
    with pytest.raises(ValueError):
        EnqueueConversation.from_intent(replace(sent, mode="read", draft_kind="record-note"))
    assert EnqueueConversation.from_intent(replace(sent, mode="draft", draft_kind="record-note"))
