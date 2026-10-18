"""Project-owned read/draft port; no SDK, repository or business-write handle."""
from dataclasses import dataclass
from enum import StrEnum
from typing import AsyncIterator, Protocol
from uuid import UUID


class Mode(StrEnum):
    READ = "read"
    DRAFT = "draft"
    CHAT = "chat"


class DraftKind(StrEnum):
    TASK = "task"
    RECORD_NOTE = "record-note"


@dataclass(frozen=True)
class AgentRequest:
    conversation_id: UUID
    text: str
    mode: Mode
    draft_kind: DraftKind = DraftKind.TASK


@dataclass(frozen=True)
class RuntimeEvent:
    cursor: int
    run_id: UUID
    type: str
    payload: dict


class AgentRuntimePort(Protocol):
    def stream(self, credentials: tuple, request: AgentRequest) -> AsyncIterator[RuntimeEvent]: ...


class AgentRejected(Exception):
    def __init__(self):
        super().__init__("Agent request rejected")
