"""Closed source fence metadata, not target admission or a transferable token."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from uuid import UUID

from .roster import identifiers


def _hash(value):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid source transfer hash")


@dataclass(frozen=True)
class SealConversationSource:
    attempt_id: UUID
    export_id: UUID
    package_hash: str
    target_workspace_id: UUID
    target_owner_id: UUID
    target_binding: str

    def __post_init__(self):
        identifiers(self.attempt_id, self.export_id, self.target_workspace_id, self.target_owner_id)
        _hash(self.package_hash)
        _hash(self.target_binding)

    def canonical(self):
        return {"command": "conversation.transfer.seal", **{
            key: str(value) if type(value) is UUID else value for key, value in vars(self).items()}}


def decode_seal(payload):
    fields = {"command", "attempt_id", "export_id", "package_hash", "target_workspace_id", "target_owner_id", "target_binding"}
    if type(payload) is not dict or set(payload) != fields or payload["command"] != "conversation.transfer.seal":
        raise ValueError("Invalid source seal command")
    values = {key: value for key, value in payload.items() if key != "command"}
    for key in ("attempt_id", "export_id", "target_workspace_id", "target_owner_id"):
        if type(values[key]) is not str:
            raise ValueError("Invalid source seal identifier")
        values[key] = UUID(values[key])
    result = SealConversationSource(**values)
    if result.canonical() != payload:
        raise ValueError("Noncanonical source seal command")
    return result


@dataclass(frozen=True)
class SourceFence:
    workspace_id: UUID
    owner_id: UUID
    authority_id: UUID
    restriction_epoch: int
    restriction_hash: str
    command: SealConversationSource
    created_at: datetime

    def __post_init__(self):
        identifiers(self.workspace_id, self.owner_id, self.authority_id)
        _hash(self.restriction_hash)
        if (type(self.restriction_epoch) is not int or not 0 <= self.restriction_epoch <= 4096
                or type(self.command) is not SealConversationSource
                or self.command.target_workspace_id == self.workspace_id or self.command.target_owner_id == self.owner_id
                or type(self.created_at) is not datetime or self.created_at.tzinfo is None
                or self.created_at.utcoffset() != timedelta(0)):
            raise ValueError("Invalid source fence")

    def canonical(self):
        return {"workspace_id": str(self.workspace_id), "owner_id": str(self.owner_id), "authority_id": str(self.authority_id),
                "restriction_epoch": self.restriction_epoch, "restriction_hash": self.restriction_hash,
                "command": self.command.canonical(), "created_at": self.created_at.isoformat()}


def decode_fence(value):
    fields = {"workspace_id", "owner_id", "authority_id", "restriction_epoch", "restriction_hash", "command", "created_at"}
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Invalid source fence fields")
    if any(type(value[key]) is not str for key in ("workspace_id", "owner_id", "authority_id", "created_at")):
        raise ValueError("Invalid source fence scalar")
    result = SourceFence(*(UUID(value[key]) for key in ("workspace_id", "owner_id", "authority_id")),
                         value["restriction_epoch"], value["restriction_hash"], decode_seal(value["command"]),
                         datetime.fromisoformat(value["created_at"]))
    if result.canonical() != value:
        raise ValueError("Noncanonical source fence")
    return result


@dataclass(frozen=True)
class CommittedSource:
    """Live QG observation of a committed freeze, never an offline capability."""
    fence: SourceFence
    fence_hash: str
    receipt_id: UUID
    root_binding: str

    def __post_init__(self):
        if type(self.fence) is not SourceFence:
            raise ValueError("Invalid committed source")
        identifiers(self.receipt_id)
        _hash(self.fence_hash)
        _hash(self.root_binding)

    def canonical(self):
        return {"fence": self.fence.canonical(), "fence_hash": self.fence_hash,
                "receipt_id": str(self.receipt_id), "root_binding": self.root_binding}
