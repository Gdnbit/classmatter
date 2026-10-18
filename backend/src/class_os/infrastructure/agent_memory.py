"""Bounded ephemeral SDK conversation memory; never Domain Fact authority."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from class_os.application.agent import AgentRejected
from class_os.application.identity import digest


@dataclass
class Conversation:
    conversation_id: UUID
    binding: tuple
    class_id: UUID
    term_id: UUID
    expires_at: datetime
    history: list = field(default_factory=list)
    active: bool = False
    turns: int = 0
    student_id: UUID | None = None


class ConversationMemory:
    def __init__(self, *, clock=lambda: datetime.now(timezone.utc)):
        self.clock = clock
        self._items = {}

    @staticmethod
    def binding(credentials):
        token, client, csrf, workspace = credentials
        return (digest(token), digest(client), digest(csrf), workspace)

    def _expire(self):
        now = self.clock()
        for key, item in tuple(self._items.items()):
            if now >= item.expires_at and not item.active:
                item.history.clear()
                del self._items[key]

    def create(self, credentials, class_id, term_id, *, student_id=None):
        self._expire()
        if (len(self._items) >= 32 or type(class_id) is not UUID or type(term_id) is not UUID
                or (student_id is not None and type(student_id) is not UUID)):
            raise AgentRejected()
        item = Conversation(uuid4(), (*self.binding(credentials), class_id, term_id, student_id),
                            class_id, term_id, self.clock() + timedelta(minutes=15), student_id=student_id)
        self._items[item.conversation_id] = item
        return item

    def get(self, credentials, conversation_id):
        self._expire()
        item = self._items.get(conversation_id)
        if (item is None or item.binding != (*self.binding(credentials), item.class_id, item.term_id, item.student_id) or self.clock() >= item.expires_at
                or item.turns >= 10):
            raise AgentRejected()
        return item

    def forget(self, credentials, conversation_id):
        self._expire()
        item = self._items.get(conversation_id)
        if (item is None or item.binding != (*self.binding(credentials), item.class_id, item.term_id, item.student_id) or item.active):
            raise AgentRejected()
        del self._items[conversation_id]

    def clear(self):
        if any(item.active for item in self._items.values()):
            raise AgentRejected()
        self._items.clear()

    def release(self, item):
        """End a run without extending TTL; drop expired live history references."""
        item.active = False
        if self.clock() >= item.expires_at:
            item.history.clear()
            if self._items.get(item.conversation_id) is item:
                del self._items[item.conversation_id]
