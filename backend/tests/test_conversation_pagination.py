"""Complete bounded pages over actual human BCG input, not Demo history."""
from uuid import uuid4

import pytest

from class_os.application.roster import CommandRejected
from class_os.domain.conversation_control import ClearConversation
from test_conversation_result_gateway import captured
from test_conversation_control import control, storage, roster, identity


@pytest.mark.db
async def test_whole_turn_pages_keep_older_sources_and_reject_changed_version(control):
    value = captured(control, "read")
    value.worker.finish_result(value.auth, value.ticket, value.sealed)
    # One actual completed tool result followed by 51 actual cancelled sends.
    # Cancellation frees each slot; no hidden model runs or forged raw history.
    for number in range(51):
        key = uuid4()
        sent = value.worker.enqueue(*value.auth, value.ids["class"], value.ids["term"], value.thread, key,
                                    f"synthetic historical cancelled input {number}", "read")
        value.worker.cancel_run(value.auth, value.ids["class"], value.ids["term"], value.thread, sent.receipt.resource_id, 1)
    args = (*value.auth, value.ids["class"], value.ids["term"], value.thread)
    first = value.query.conversation_page(*args)
    assert first.next_before == 3 and first.value.history.truncated
    assert len(first.value.history.messages) == 50 and not first.value.results
    assert len(first.turns) == 50 and all(row.run.state == "cancelled" for row in first.turns)
    second = value.query.conversation_page(*args, before_ordinal=first.next_before, expected_version=first.value.history.version)
    assert second.next_before is None and not second.value.history.truncated
    assert len(second.value.history.messages) == 3 and len(second.value.results) == 1
    assert len(second.turns) == 2 and second.turns[0].run.state == "completed"
    assert {row.turn_id for row in first.turns} == {row.turn_id for row in first.value.history.messages}
    assert {row.turn_id for row in second.turns} == {row.turn_id for row in second.value.history.messages}
    assert len({row.client_request_id for row in first.turns + second.turns}) == 52
    assert len({row.run.run_id for row in first.turns + second.turns}) == 52
    assert second.value.results[0].result == value.result
    one = {row.turn_id for row in first.value.history.messages}
    two = {row.turn_id for row in second.value.history.messages}
    assert not one & two and len(one | two) == 52
    assert len(first.value.message_attributions) == 50 and len(second.value.message_attributions) == 3
    from class_os.interfaces.http.durable_conversation import create_durable_app
    from class_os.interfaces.http.settings import Settings
    from class_os.infrastructure.agent import PydanticAgentRuntime
    from test_durable_conversation_http import client
    value.app = create_durable_app(Settings(), worker=value.worker, query=value.query, sdk=PydanticAgentRuntime(value.query))
    path = f"/api/workspaces/{value.auth[3]}/conversation-d1/classes/{value.ids['class']}/terms/{value.ids['term']}/conversations/{value.thread}"
    async with client(value) as api:
        wire = await api.get(path + f"/pages/{first.value.history.version}/{first.next_before}")
        assert wire.status_code == 200, wire.text
        assert wire.json()["student_id"] is None and wire.json()["class_id"] == str(value.ids["class"])
        assert len(wire.json()["history"]["messages"]) == 3 and len(wire.json()["results"]) == 1
        assert wire.json()["results"][0]["result"]["sources"][0]["receipt_id"] == str(value.result.sources[0].receipt_id)
        resumed = await api.get(path + f"/history/pages/{first.value.history.version}/{first.next_before}")
        assert resumed.status_code == 200, resumed.text
        assert [row["turn_id"] for row in resumed.json()["turns"]] == [str(row.turn_id) for row in second.turns]
    old_version = first.value.history.version
    for before, version in ((True, old_version), (0, old_version), (10001, old_version),
                            (3, True), (3, old_version - 1), (None, old_version), (3, None)):
        with pytest.raises(CommandRejected):
            value.query.conversation_page(*args, before_ordinal=before, expected_version=version)
    value.worker.rename_conversation(*value.auth, value.ids["class"], value.ids["term"], value.thread, uuid4(), old_version, "synthetic updated title")
    with pytest.raises(CommandRejected):
        value.query.conversation_page(*args, before_ordinal=3, expected_version=old_version)
    current = value.query.conversation_page(*args)
    command = ClearConversation(value.thread, value.ids["class"], value.ids["term"], current.value.history.version)
    proposal = value.worker.preview(*value.auth, command)
    approval = value.worker.approve(*value.auth, proposal.proposal_id, proposal.payload_hash)
    value.worker.commit(*value.auth, proposal.proposal_id, uuid4(), approval)
    with pytest.raises(CommandRejected):
        value.query.conversation_page(*args, before_ordinal=3, expected_version=current.value.history.version)
    cleared = value.query.conversation_page(*args)
    assert cleared.next_before is None and not cleared.value.history.messages and not cleared.value.results
    assert not cleared.turns
    async with client(value) as api:
        hidden = await api.get(path + "/history")
        assert hidden.status_code == 200 and not hidden.json()["turns"]
        assert (await api.get(path + f"/history/pages/{old_version}/{first.next_before}")).status_code == 409


@pytest.mark.db
async def test_list_pages_preserve_attribution_and_invalidate_on_any_thread_change(control):
    from test_durable_conversation_http import setup, client
    value = setup(control)
    for number in range(51):
        value.worker.create_conversation(*value.auth, value.ids["class"], value.ids["term"], uuid4(), uuid4(), f"synthetic list {number}")
    args = (*value.auth, value.ids["class"], value.ids["term"])
    first = value.query.conversation_listing(*args)
    assert len(first.items) == 50 and first.next_offset == 50
    second = value.query.conversation_listing(*args, snapshot=first.snapshot, offset=50)
    assert len(second.items) == 2 and second.next_offset is None and second.snapshot == first.snapshot
    assert len({row["thread_id"] for row in first.items + second.items}) == 52
    assert all(row["attribution"]["created_by"] == str(value.ids["owner"]) for row in first.items + second.items)
    async with client(value) as api:
        response = await api.get(value.base + f"/conversations/pages/{first.snapshot}/50")
        assert response.status_code == 200, response.text
        assert len(response.json()["data"]) == 2 and response.json()["next_offset"] is None
    for snapshot, offset in ((None, 50), (first.snapshot, True), (first.snapshot, 1), (first.snapshot, -50),
                             (first.snapshot, 10000), ("f" * 64, 50), ("x" * 64, 50)):
        with pytest.raises(CommandRejected):
            value.query.conversation_listing(*args, snapshot=snapshot, offset=offset)
    changed = second.items[-1]
    value.worker.rename_conversation(*value.auth, value.ids["class"], value.ids["term"], changed["thread_id"], uuid4(), changed["version"], "synthetic list edit")
    with pytest.raises(CommandRejected):
        value.query.conversation_listing(*args, snapshot=first.snapshot, offset=50)
