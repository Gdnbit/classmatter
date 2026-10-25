"""Fixed server run metadata, never an Agent tool or a transferable authority."""
from dataclasses import dataclass, fields, field
from datetime import datetime, timedelta
from types import MappingProxyType
from uuid import UUID

from .conversation_exit import _hash, _uuid, _instant
from .durable_conversation import ConversationScope, ConversationRun, SendIntent
from .roster import identifiers


def utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("UTC run timestamp required")
    return value


@dataclass(frozen=True)
class RunMetadata:
    thread_id: UUID
    class_id: UUID
    term_id: UUID
    run_id: UUID
    expected_version: int

    def __post_init__(self):
        identifiers(self.thread_id, self.class_id, self.term_id, self.run_id)
        if type(self.expected_version) is not int or not 1 <= self.expected_version < 2147483647:
            raise ValueError("Invalid run version")

    def canonical(self):
        return {"command": self.command, **{field.name: value.isoformat() if type(value) is datetime else
            str(value) if type(value) is UUID else value for field in fields(self) for value in (getattr(self, field.name),)}}


@dataclass(frozen=True)
class ClaimRun(RunMetadata):
    generation: UUID
    lease_until: datetime
    request_hash: str
    command = "conversation.run.claim"

    def __post_init__(self):
        super().__post_init__()
        identifiers(self.generation)
        utc(self.lease_until)
        _hash(self.request_hash)


@dataclass(frozen=True)
class FinishRun(RunMetadata):
    generation: UUID
    state: str
    output_hash: str | None
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    command = "conversation.run.finish"

    def __post_init__(self):
        super().__post_init__()
        identifiers(self.generation)
        if type(self.state) is not str or self.state not in ("completed", "failed", "cancelled", "unknown"):
            raise ValueError("Invalid worker outcome")
        if self.state == "completed":
            _hash(self.output_hash)
        elif self.output_hash is not None:
            raise ValueError("Unfinished output must not be persisted")
        for value in (self.duration_ms, self.input_tokens, self.output_tokens):
            if value is not None and (type(value) is not int or not 0 <= value <= 2147483647):
                raise ValueError("Invalid bounded run metric")


@dataclass(frozen=True)
class CancelRun(RunMetadata):
    command = "conversation.run.cancel"


@dataclass(frozen=True)
class ReconcileRun(RunMetadata):
    command = "conversation.run.reconcile"


COMMANDS = MappingProxyType({value.command: value for value in (ClaimRun, FinishRun, CancelRun, ReconcileRun)})


def decode_run(value):
    if type(value) is not dict or type(value.get("command")) is not str or value["command"] not in COMMANDS:
        raise ValueError("Unregistered run command")
    command = COMMANDS[value["command"]]
    columns = {field.name for field in fields(command)}
    if set(value) != columns | {"command"}:
        raise ValueError("Unknown run command fields")
    args = {key: value[key] for key in columns}
    for key in ("thread_id", "class_id", "term_id", "run_id", "generation"):
        if key in args:
            args[key] = _uuid(args[key])
    if "lease_until" in args:
        args["lease_until"] = _instant(args["lease_until"])
    result = command(**args)
    if result.canonical() != value:
        raise ValueError("Noncanonical run command")
    return result


@dataclass(frozen=True)
class ClaimedRun:
    # Private process-local data. Credentials/approvals are never fields, and
    # constructing this object alone grants no SQL/dispatch permission.
    scope: ConversationScope
    turn_id: UUID
    intent: SendIntent = field(repr=False)
    run: ConversationRun

    def __post_init__(self):
        if (type(self.scope) is not ConversationScope or type(self.intent) is not SendIntent
                or self.intent.scope != self.scope or type(self.run) is not ConversationRun
                or self.run.state != "running" or self.run.version != 2):
            raise ValueError("Invalid private claim")
        identifiers(self.turn_id)
