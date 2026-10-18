from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any, Protocol


class RouteMode(StrEnum):
    ANSWER_ONLY = "answer_only"
    READ = "read"
    DRAFT_WRITE = "draft_write"
    CLARIFY = "clarify"


class ToolRisk(StrEnum):
    READ_ONLY = "READ_ONLY"
    DRAFT_ONLY = "DRAFT_ONLY"
    MUTATING_REVERSIBLE = "MUTATING_REVERSIBLE"
    MUTATING_HIGH_IMPACT = "MUTATING_HIGH_IMPACT"
    EXTERNAL_SIDE_EFFECT = "EXTERNAL_SIDE_EFFECT"


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    risk: ToolRisk
    domain: str
    description: str


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    request_id: str
    conversation_id: str
    run_id: str
    workspace_id: str
    user_text: str
    route_mode: RouteMode
    requested_tools: frozenset[str] = frozenset()
    timeout_seconds: float = 2.0


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    cursor: int
    type: str
    run_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    status: str
    answer: str | None
    events: tuple[RuntimeEvent, ...]
    source_refs: tuple[str, ...] = ()
    draft: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AuditRecord:
    correlation_id: str
    workspace_id: str
    model_adapter: str
    tool_names: tuple[str, ...]
    source_refs: tuple[str, ...]
    outcome: str


class AgentRuntimePort(Protocol):
    async def run(self, request: RuntimeRequest) -> RuntimeResult: ...

    def stream(self, request: RuntimeRequest) -> AsyncIterator[RuntimeEvent]: ...


class QueryGatewayPort(Protocol):
    async def attention_list(self, workspace_id: str) -> dict[str, Any]: ...


class DraftBuilderPort(Protocol):
    async def build_task_draft(self, workspace_id: str, title: str) -> dict[str, Any]: ...
