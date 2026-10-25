"""Closed same-host handoff evidence. No target admission or credentials."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from .conversation_exit import _uuid, _hash, _instant
from .source_transfer import CommittedSource, decode_fence
from .target_import import TargetFence, decode_target


def _time(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("Invalid handoff time")


@dataclass(frozen=True)
class CommittedStage:
    fence: TargetFence
    fence_hash: str
    receipt_id: UUID
    root_binding: str
    snapshot_hash: str
    imported_at: datetime

    def __post_init__(self):
        if type(self.fence) is not TargetFence or type(self.receipt_id) is not UUID:
            raise ValueError("Invalid committed target")
        for value in (self.fence_hash, self.root_binding, self.snapshot_hash):
            _hash(value)
        _time(self.imported_at)
        if self.imported_at < self.fence.created_at:
            raise ValueError("Target import predates its fence")

    def canonical(self):
        return {"fence": self.fence.canonical(), "fence_hash": self.fence_hash, "receipt_id": str(self.receipt_id),
                "root_binding": self.root_binding, "snapshot_hash": self.snapshot_hash, "imported_at": self.imported_at.isoformat()}


def decode_stage(value):
    if type(value) is not dict or set(value) != {"fence", "fence_hash", "receipt_id", "root_binding", "snapshot_hash", "imported_at"}:
        raise ValueError("Invalid target proof fields")
    result = CommittedStage(decode_target(value["fence"]), value["fence_hash"], _uuid(value["receipt_id"]),
                            value["root_binding"], value["snapshot_hash"], _instant(value["imported_at"]))
    if result.canonical() != value:
        raise ValueError("Noncanonical target proof")
    return result


@dataclass(frozen=True)
class RetireConversationSource:
    attempt_id: UUID
    expected_stage_hash: str

    def __post_init__(self):
        if type(self.attempt_id) is not UUID:
            raise ValueError("Invalid retirement attempt")
        _hash(self.expected_stage_hash)

    def canonical(self):
        return {"command": "conversation.transfer.retire", "attempt_id": str(self.attempt_id),
                "expected_stage_hash": self.expected_stage_hash}


def decode_retirement(payload):
    if (type(payload) is not dict or set(payload) != {"command", "attempt_id", "expected_stage_hash"}
            or payload["command"] != "conversation.transfer.retire"):
        raise ValueError("Unregistered retirement command")
    result = RetireConversationSource(_uuid(payload["attempt_id"]), payload["expected_stage_hash"])
    if result.canonical() != payload:
        raise ValueError("Noncanonical retirement command")
    return result


@dataclass(frozen=True)
class RetirementFence:
    source: CommittedSource
    stage: CommittedStage
    command: RetireConversationSource
    created_at: datetime

    def __post_init__(self):
        if type(self.source) is not CommittedSource or type(self.stage) is not CommittedStage or type(self.command) is not RetireConversationSource:
            raise ValueError("Live typed source and target observations required")
        _time(self.created_at)
        source, stage = self.source, self.stage
        if (self.command.attempt_id != source.fence.command.attempt_id or stage.fence.command.attempt_id != self.command.attempt_id
                or self.command.expected_stage_hash != stage.snapshot_hash
                or stage.fence.command.source_fence_hash != source.fence_hash or stage.fence.source_receipt_id != source.receipt_id
                or stage.fence.command.package_hash != source.fence.command.package_hash
                or stage.fence.workspace_id != source.fence.command.target_workspace_id
                or stage.fence.owner_id != source.fence.command.target_owner_id
                or stage.root_binding != source.fence.command.target_binding or stage.root_binding == source.root_binding
                or not source.fence.created_at <= stage.fence.created_at <= stage.imported_at <= self.created_at):
            raise ValueError("Source and committed target are not the same handoff")

    def canonical(self):
        return {"source": self.source.canonical(), "stage": self.stage.canonical(),
                "command": self.command.canonical(), "created_at": self.created_at.isoformat()}


def decode_retirement_fence(value):
    if type(value) is not dict or set(value) != {"source", "stage", "command", "created_at"}:
        raise ValueError("Invalid retirement fields")
    source = value["source"]
    if type(source) is not dict or set(source) != {"fence", "fence_hash", "receipt_id", "root_binding"}:
        raise ValueError("Invalid source proof fields")
    committed = CommittedSource(decode_fence(source["fence"]), source["fence_hash"], _uuid(source["receipt_id"]), source["root_binding"])
    result = RetirementFence(committed, decode_stage(value["stage"]), decode_retirement(value["command"]), _instant(value["created_at"]))
    if result.canonical() != value:
        raise ValueError("Noncanonical retirement proof")
    return result


@dataclass(frozen=True)
class CommittedRetirement:
    fence: RetirementFence
    proof_hash: str
    receipt_id: UUID

    def __post_init__(self):
        if type(self.fence) is not RetirementFence or type(self.receipt_id) is not UUID:
            raise ValueError("Invalid committed retirement")
        _hash(self.proof_hash)
