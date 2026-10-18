from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from class_os.application.agent import AgentRejected
from class_os.infrastructure.agent_memory import ConversationMemory


def test_memory_ttl_binding_capacity_turn_budget_and_forget():
    clock = [datetime.now(timezone.utc)]
    memory = ConversationMemory(clock=lambda: clock[0])
    credentials = ("synthetic-token", "synthetic-client", "synthetic-csrf", uuid4())
    item = memory.create(credentials, uuid4(), uuid4())
    assert memory.get(credentials, item.conversation_id) is item
    for field in range(4):
        other = list(credentials)
        other[field] = uuid4() if field == 3 else "another-synthetic-value"
        with pytest.raises(AgentRejected):
            memory.get(tuple(other), item.conversation_id)
    item.active = True
    with pytest.raises(AgentRejected):
        memory.forget(credentials, item.conversation_id)
    item.active = False
    item.turns = 10
    with pytest.raises(AgentRejected):
        memory.get(credentials, item.conversation_id)
    clock[0] += timedelta(minutes=15)
    with pytest.raises(AgentRejected):
        memory.get(credentials, item.conversation_id)
    assert not memory._items
    for _ in range(32):
        memory.create(credentials, uuid4(), uuid4())
    with pytest.raises(AgentRejected):
        memory.create(credentials, uuid4(), uuid4())


def test_run_release_does_not_extend_ttl_and_clears_expired_history_references():
    clock = [datetime.now(timezone.utc)]
    memory = ConversationMemory(clock=lambda: clock[0])
    credentials = ("synthetic-token", "synthetic-client", "synthetic-csrf", uuid4())
    item = memory.create(credentials, uuid4(), uuid4())
    expires_at = item.expires_at
    item.active = True
    item.history.append("synthetic-history")
    memory.release(item)
    assert not item.active and item.history == ["synthetic-history"] and item.expires_at == expires_at
    assert memory.get(credentials, item.conversation_id) is item
    item.active = True
    clock[0] = expires_at
    memory._expire()
    assert item.conversation_id in memory._items
    memory.release(item)
    assert item.history == [] and not item.active and item.conversation_id not in memory._items
