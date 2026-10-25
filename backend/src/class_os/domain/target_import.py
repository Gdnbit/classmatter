"""Bounded native exit candidates and terminal-only, single-hop staging."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from types import MappingProxyType
from uuid import UUID

import rfc8785

from .conversation_exit import MAX_BYTES, _hash, _uuid, _instant
from .conversation_exit_v3 import validate_v3
from .durable_conversation import ACTIVE_STATES
from .exit_package import CORE_COLUMNS, PRIMARY_KEYS, AUDIT_COLUMNS, checksum
from .roster import identifiers
from .source_transfer import CommittedSource


IMPORT_COLUMNS = MappingProxyType({
    "conversation_import": ("workspace_id", "attempt_id", "restorer_id", "source_workspace_id", "source_owner_id",
        "source_authority_id", "source_epoch", "source_head_hash", "source_fence_hash", "source_receipt_id",
        "source_root_binding", "package_hash", "target_binding", "source_sealed_at", "imported_at", "phase"),
    "conversation_provenance": ("workspace_id", "attempt_id", "entity_kind", "thread_id", "resource_id", "source_version", "source_hash"),
    "conversation_source_audit": ("workspace_id", "attempt_id", "source_workspace_id", *AUDIT_COLUMNS[1:]),
})
IMPORT_KEYS = MappingProxyType({"conversation_import": ("attempt_id",),
    "conversation_provenance": ("entity_kind", "thread_id", "resource_id", "source_version"),
    "conversation_source_audit": ("attempt_id", "occurred_at", "event_id")})
ENTITY_KEYS = MappingProxyType({**{key: value[0] for key, value in PRIMARY_KEYS.items() if key != "workspace"},
    "conversation_thread": "thread_id", "conversation_turn": "turn_id",
    "conversation_message": "message_id", "conversation_run": "run_id"})


@dataclass(frozen=True)
class StageConversationImport:
    attempt_id: UUID
    package_hash: str
    source_fence_hash: str

    def __post_init__(self):
        identifiers(self.attempt_id)
        _hash(self.package_hash)
        _hash(self.source_fence_hash)

    def canonical(self):
        return {"command": "conversation.import.stage", "attempt_id": str(self.attempt_id),
                "package_hash": self.package_hash, "source_fence_hash": self.source_fence_hash}


def decode_import(payload):
    if (type(payload) is not dict or set(payload) != {"command", "attempt_id", "package_hash", "source_fence_hash"}
            or payload["command"] != "conversation.import.stage"):
        raise ValueError("Invalid import command")
    command = StageConversationImport(_uuid(payload["attempt_id"]), payload["package_hash"], payload["source_fence_hash"])
    if command.canonical() != payload:
        raise ValueError("Noncanonical import command")
    return command


def native_candidate(bundle):
    if type(bundle) is not dict:
        raise ValueError("Invalid native candidate")
    if bundle.get("schema_version") == "classmatter.synthetic-exit.v3":
        validate_v3(bundle)
    else:
        from .conversation_exit_v4 import validate_v4
        validate_v4(bundle)
        if any(bundle["recovery"].values()):
            raise ValueError("Multi-hop import is not yet admitted")
    if any(row["state"] in ACTIVE_STATES for row in bundle["conversations"]["conversation_run"]):
        raise ValueError("Active source runs cannot be staged")
    return bundle


@dataclass(frozen=True)
class RecoveryCandidate:
    # The store owns immutable canonical bytes, not a caller-mutatable SDK dict.
    encoded: bytes

    def __post_init__(self):
        if type(self.encoded) is not bytes or not 0 < len(self.encoded) <= MAX_BYTES:
            raise ValueError("Invalid bounded candidate")
        bundle = json.loads(self.encoded.decode("utf-8"))
        if rfc8785.dumps(native_candidate(bundle)) != self.encoded:
            raise ValueError("Noncanonical candidate")

    @classmethod
    def from_bundle(cls, bundle):
        return cls(rfc8785.dumps(native_candidate(bundle)))

    def bundle(self):
        return json.loads(self.encoded.decode("utf-8"))

    def match(self, command, source, workspace, owner, root_binding, now):
        if type(command) is not StageConversationImport or type(source) is not CommittedSource:
            raise ValueError("Live committed source required")
        bundle, fence = self.bundle(), source.fence
        proof = bundle["restriction_evidence"]
        if (command.attempt_id != fence.command.attempt_id or command.package_hash != bundle["package_checksum"]
                or command.package_hash != fence.command.package_hash or command.source_fence_hash != source.fence_hash
                or workspace != fence.command.target_workspace_id or owner != fence.command.target_owner_id
                or root_binding != fence.command.target_binding or str(fence.workspace_id) != bundle["workspace_id"]
                or bundle["actor_refs"] != [str(fence.owner_id)] or str(fence.authority_id) != proof["authority_id"]
                or fence.restriction_epoch != proof["epoch"] or fence.restriction_hash != proof["source_head_hash"]
                or not _instant(bundle["created_at"]) <= fence.created_at <= now):
            raise ValueError("Candidate is not bound to this live source and target")
        return bundle


@dataclass(frozen=True)
class TargetFence:
    workspace_id: UUID
    owner_id: UUID
    authority_id: UUID
    initial_head_hash: str
    command: StageConversationImport
    source_receipt_id: UUID
    created_at: datetime

    def __post_init__(self):
        identifiers(self.workspace_id, self.owner_id, self.authority_id, self.source_receipt_id)
        _hash(self.initial_head_hash)
        if (type(self.command) is not StageConversationImport or type(self.created_at) is not datetime
                or self.created_at.tzinfo is None or self.created_at.utcoffset() != timedelta(0)):
            raise ValueError("Invalid target fence")

    def canonical(self):
        return {"workspace_id": str(self.workspace_id), "owner_id": str(self.owner_id), "authority_id": str(self.authority_id),
                "initial_head_hash": self.initial_head_hash, "command": self.command.canonical(),
                "source_receipt_id": str(self.source_receipt_id), "created_at": self.created_at.isoformat()}


def decode_target(value):
    if type(value) is not dict or set(value) != {"workspace_id", "owner_id", "authority_id", "initial_head_hash", "command", "source_receipt_id", "created_at"}:
        raise ValueError("Invalid target fence fields")
    result = TargetFence(*(_uuid(value[k]) for k in ("workspace_id", "owner_id", "authority_id")),
                         value["initial_head_hash"], decode_import(value["command"]), _uuid(value["source_receipt_id"]), _instant(value["created_at"]))
    if result.canonical() != value:
        raise ValueError("Noncanonical target fence")
    return result


def provenance_rows(bundle, workspace, attempt):
    rows = []
    for kind, key in ENTITY_KEYS.items():
        for row in bundle["core" if kind in CORE_COLUMNS else "conversations"][kind]:
            rows.append({"workspace_id": str(workspace), "attempt_id": str(attempt), "entity_kind": kind,
                         "thread_id": row["thread_id"] if kind in ("conversation_turn", "conversation_message", "conversation_run") else None,
                         "resource_id": row[key], "source_version": row.get("version", 0), "source_hash": checksum(row)})
    return rows
