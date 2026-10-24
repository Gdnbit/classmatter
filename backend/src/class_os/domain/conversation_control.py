"""Closed post-R1 human controls, not R1 commands or Agent tools."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .roster import identifiers
from .durable_conversation import VisibleMessage


@dataclass(frozen=True)
class InitializeConversationControl:
    authority_id: UUID

    def __post_init__(self):
        identifiers(self.authority_id)

    def canonical(self):
        return {"command": "conversation.control.initialize", "authority_id": str(self.authority_id)}


@dataclass(frozen=True)
class ClearConversation:
    thread_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int

    def __post_init__(self):
        identifiers(self.thread_id, self.class_id, self.term_id)
        if type(self.expected_version) is not int or not 1 <= self.expected_version < 2147483647:
            raise ValueError("Invalid conversation version")

    def canonical(self):
        return {"command": "conversation.clear", "thread_id": str(self.thread_id), "class_id": str(self.class_id),
                "term_id": str(self.term_id), "expected_version": self.expected_version}


def decode_control(payload):
    if type(payload) is not dict:
        raise ValueError("Invalid conversation control")
    if set(payload) == {"command", "authority_id"} and payload["command"] == "conversation.control.initialize":
        value = InitializeConversationControl(_identifier(payload["authority_id"]))
    elif set(payload) == {"command", "thread_id", "class_id", "term_id", "expected_version"} and payload["command"] == "conversation.clear":
        value = ClearConversation(*(_identifier(payload[key]) for key in ("thread_id", "class_id", "term_id")), payload["expected_version"])
    else:
        raise ValueError("Unregistered conversation control")
    if value.canonical() != payload:
        raise ValueError("Noncanonical conversation control")
    return value


def _identifier(value):
    if type(value) is not str:
        raise ValueError("Invalid conversation identifier")
    return UUID(value)


@dataclass(frozen=True)
class HistoryMessage:
    message_id: UUID
    turn_id: UUID
    created_at: datetime
    content: VisibleMessage


@dataclass(frozen=True)
class ConversationHistory:
    thread_id: UUID
    title: str
    status: str
    version: int
    messages: tuple[HistoryMessage, ...]
    truncated: bool
