"""Closed historical output DTOs, never facts, approvals or a generic JSON store.

This registry is v6-only. Historical exit/import registries must not be widened.
Source syntax alone is not proof: the BCG must verify the original QG receipt
and this run's authorized scope/time window before persistence/release.
"""
from dataclasses import dataclass, field, fields
from datetime import datetime
from types import MappingProxyType
from uuid import UUID, uuid4

from .activity import CreateTask
from .conversation_exit import _hash, _uuid, _instant
from .conversation_worker import RunMetadata, utc
from .durable_conversation import ConversationScope, SendIntent, VisibleMessage
from .exit_package import checksum
from .roster import identifiers


RESULT_COLUMNS = MappingProxyType({
    "conversation_result_receipt": ("workspace_id", "thread_id", "turn_id", "message_id", "message_role", "protocol", "text_hash", "result_hash", "created_at", "recorded_at"),
    "conversation_query_source": ("workspace_id", "thread_id", "turn_id", "message_id", "message_role", "source_id", "ordinal",
        "source_workspace_id", "source_owner_id", "receipt_id", "projection_hash", "as_of", "created_at"),
    "conversation_task_draft": ("workspace_id", "thread_id", "turn_id", "message_id", "message_role", "draft_id", "title", "title_hash", "visibility", "created_at"),
})
RESULT_KEYS = MappingProxyType({
    "conversation_result_receipt": ("thread_id", "turn_id", "message_id"),
    "conversation_query_source": ("thread_id", "turn_id", "message_id", "ordinal", "source_id"),
    "conversation_task_draft": ("thread_id", "turn_id", "message_id", "draft_id"),
})
RESULT_ENTITY_KEYS = MappingProxyType({"conversation_result_receipt": "message_id", "conversation_query_source": "source_id", "conversation_task_draft": "draft_id"})


def result_canonical(text_hash, sources, draft):
    return {"schema_version": "classmatter.conversation-result.v1", "text_hash": text_hash,
            "sources": sources, "draft": draft}


def draft_metadata(draft):
    if draft is None:
        return None
    return {**{key: value for key, value in draft.canonical().items() if key != "title"}, "title_hash": checksum(draft.title)}


@dataclass(frozen=True)
class QuerySource:
    source_id: UUID
    source_workspace_id: UUID
    source_owner_id: UUID
    receipt_id: UUID
    projection_hash: str
    as_of: datetime

    def __post_init__(self):
        identifiers(self.source_id, self.source_workspace_id, self.source_owner_id, self.receipt_id)
        _hash(self.projection_hash)
        utc(self.as_of)

    def canonical(self):
        return {item.name: str(value) if type(value) is UUID else value.isoformat() if type(value) is datetime else value
                for item in fields(self) for value in (getattr(self, item.name),)}

    def tool_ref(self):
        return {"entity": "query_receipt", "id": str(self.receipt_id), "version": 1,
                "projection_hash": self.projection_hash, "as_of": self.as_of.isoformat()}

    @classmethod
    def from_tool(cls, scope, value, *, source_id=None):
        if (type(scope) is not ConversationScope or type(value) is not dict
                or set(value) != {"entity", "id", "version", "projection_hash", "as_of"}
                or value["entity"] != "query_receipt" or type(value["version"]) is not int or value["version"] != 1):
            raise ValueError("Unregistered query source")
        result = cls(source_id if source_id is not None else uuid4(), scope.workspace_id, scope.owner_id,
                     _uuid(value["id"]), value["projection_hash"], _instant(value["as_of"]))
        if result.tool_ref() != value:
            raise ValueError("Noncanonical query source")
        return result


@dataclass(frozen=True)
class ProducedResult:
    text: str = field(repr=False)
    sources: tuple[QuerySource, ...] = ()
    draft: CreateTask | None = field(default=None, repr=False)

    def __post_init__(self):
        VisibleMessage("assistant", "assistant-unverified", self.text)
        if len(self.text) > 4000 or type(self.sources) is not tuple or len(self.sources) > 2:
            raise ValueError("Unbounded output")
        if any(type(source) is not QuerySource for source in self.sources):
            raise ValueError("Unknown query source")
        keys = [(source.source_workspace_id, source.receipt_id) for source in self.sources]
        if len(set(keys)) != len(keys) or len({source.source_id for source in self.sources}) != len(keys):
            raise ValueError("Duplicate query source")
        if self.draft is not None and (type(self.draft) is not CreateTask or self.draft.due_at is not None
                or self.draft.student_id is not None or self.draft.source_record_id is not None):
            raise ValueError("Only the existing title-only task candidate is supported")

    def validate_intent(self, intent):
        if type(intent) is not SendIntent or intent.draft_kind != "task":
            raise ValueError("Exact send intent required")
        scope = intent.scope
        if any(source.source_workspace_id != scope.workspace_id or source.source_owner_id != scope.owner_id for source in self.sources):
            raise ValueError("Foreign query source")
        if intent.mode == "read":
            if not self.sources or self.draft is not None:
                raise ValueError("Read requires fresh verified query receipts, not a draft")
        elif intent.mode == "draft":
            if (intent.draft_kind != "task" or scope.student_id is not None or self.sources or self.draft is None
                    or self.draft.class_id != scope.class_id or self.draft.term_id != scope.term_id):
                raise ValueError("Draft scope or kind changed")
        elif self.sources or self.draft is not None or scope.student_id is not None:
            raise ValueError("Chat does not create sources or task candidates")

    def canonical(self):
        return result_canonical(checksum(self.text), [source.canonical() for source in self.sources], draft_metadata(self.draft))

    @property
    def result_hash(self):
        return checksum(self.canonical())


@dataclass(frozen=True)
class FinishResult(RunMetadata):
    generation: UUID
    result_hash: str
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    command = "conversation.run.finish-result"
    state = "completed"

    def __post_init__(self):
        super().__post_init__()
        identifiers(self.generation)
        _hash(self.result_hash)
        for value in (self.duration_ms, self.input_tokens, self.output_tokens):
            if value is not None and (type(value) is not int or not 0 <= value <= 2147483647):
                raise ValueError("Invalid bounded result metric")


def decode_finish_result(value):
    columns = {item.name for item in fields(FinishResult)}
    if (type(value) is not dict or set(value) != columns | {"command"}
            or value["command"] != FinishResult.command):
        raise ValueError("Unregistered result command")
    args = {key: value[key] for key in columns}
    for key in ("thread_id", "class_id", "term_id", "run_id", "generation"):
        args[key] = _uuid(args[key])
    result = FinishResult(**args)
    if result.canonical() != value:
        raise ValueError("Noncanonical result command")
    return result
