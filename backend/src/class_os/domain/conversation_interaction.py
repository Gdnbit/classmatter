"""Closed human interaction metadata; never a model tool or text archive."""
from dataclasses import dataclass, fields
from types import MappingProxyType
from uuid import UUID

from .conversation_exit import _hash, _uuid
from .durable_conversation import SendIntent
from .roster import identifiers


class Metadata:
    def canonical(self):
        return {"command": self.command, **{field.name: str(value) if type(value) is UUID else value
            for field in fields(self) for value in (getattr(self, field.name),)}}


@dataclass(frozen=True)
class CreateConversation(Metadata):
    thread_id: UUID
    class_id: UUID
    term_id: UUID
    title_hash: str
    student_id: UUID | None = None
    command = "conversation.create"

    def __post_init__(self):
        identifiers(self.thread_id, self.class_id, self.term_id)
        if self.student_id is not None:
            identifiers(self.student_id)
        _hash(self.title_hash)


@dataclass(frozen=True)
class RenameConversation(Metadata):
    thread_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    title_hash: str
    command = "conversation.rename"

    def __post_init__(self):
        _versioned_scope(self)
        _hash(self.title_hash)


@dataclass(frozen=True)
class ArchiveConversation(Metadata):
    thread_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    command = "conversation.archive"

    def __post_init__(self):
        _versioned_scope(self)


def _versioned_scope(value):
    identifiers(value.thread_id, value.class_id, value.term_id)
    if type(value.expected_version) is not int or not 1 <= value.expected_version < 2147483647:
        raise ValueError("Invalid conversation version")


@dataclass(frozen=True)
class EnqueueConversation(Metadata):
    thread_id: UUID
    class_id: UUID
    term_id: UUID
    student_id: UUID | None
    client_request_id: UUID
    request_hash: str
    mode: str
    draft_kind: str
    command = "conversation.enqueue"

    def __post_init__(self):
        identifiers(self.thread_id, self.class_id, self.term_id, self.client_request_id)
        if self.student_id is not None:
            identifiers(self.student_id)
        _hash(self.request_hash)
        if (type(self.mode) is not str or self.mode not in ("read", "draft", "chat")
                or type(self.draft_kind) is not str or self.draft_kind not in ("task", "record-note")
                or self.mode != "draft" and self.draft_kind != "task"):
            raise ValueError("Unsupported queued interaction")

    @classmethod
    def from_intent(cls, intent):
        if type(intent) is not SendIntent:
            raise ValueError("Exact human send intent required")
        return cls(intent.thread_id, intent.scope.class_id, intent.scope.term_id, intent.scope.student_id,
                   intent.client_request_id, intent.request_hash, intent.mode, intent.draft_kind)

    def matches(self, intent):
        return type(intent) is SendIntent and self == type(self).from_intent(intent)


COMMANDS = MappingProxyType({value.command: value for value in (CreateConversation, RenameConversation, ArchiveConversation, EnqueueConversation)})


def decode_interaction(value):
    if type(value) is not dict or type(value.get("command")) is not str or value["command"] not in COMMANDS:
        raise ValueError("Unregistered conversation interaction")
    command = COMMANDS[value["command"]]
    columns = {field.name for field in fields(command)}
    if set(value) != columns | {"command"}:
        raise ValueError("Unknown interaction fields")
    args = {key: value[key] for key in columns}
    for key in ("thread_id", "class_id", "term_id", "student_id", "client_request_id"):
        if key in args and args[key] is not None:
            args[key] = _uuid(args[key])
    result = command(**args)
    if result.canonical() != value:
        raise ValueError("Noncanonical conversation interaction")
    return result
