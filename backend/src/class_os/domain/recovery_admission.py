"""Fixed recovery origin fingerprints; never a generic fact/schema store."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from uuid import UUID

from .conversation_exit import _uuid, _hash, _instant, MAX_ROWS
from .exit_package import CORE_COLUMNS, checksum
from .target_import import IMPORT_COLUMNS, IMPORT_KEYS, ENTITY_KEYS
from .source_retirement import CommittedRetirement, decode_retirement_fence


ADMISSION_COLUMNS = MappingProxyType({
    "conversation_admission": ("workspace_id", "attempt_id", "owner_id", "authority_id", "target_binding",
        "retirement_hash", "retirement_receipt_id", "stage_hash", "stage_receipt_id", "target_fence_hash",
        "origins_hash", "origin_count", "batch_hash", "source_audit_hash", "created_at", "receipt_id", "proof_hash"),
    "conversation_origin": (*IMPORT_COLUMNS["conversation_provenance"], "identity_hash", "body_hash", "source_open", "initial_state"),
})
RECOVERY_COLUMNS = MappingProxyType({**IMPORT_COLUMNS, **ADMISSION_COLUMNS})
RECOVERY_KEYS = MappingProxyType({**IMPORT_KEYS, "conversation_admission": ("attempt_id",),
    "conversation_origin": IMPORT_KEYS["conversation_provenance"]})
MUTABLE = MappingProxyType({
    "academic_term": frozenset({"name", "start_date", "end_date", "status", "version", "updated_by", "updated_at"}),
    "school_class": frozenset({"name", "status", "version", "updated_by", "updated_at"}),
    "student": frozenset({"name", "status", "version", "updated_by", "updated_at"}),
    "enrollment": frozenset({"status", "valid_to", "version", "updated_by", "updated_at"}),
    "student_identifier": frozenset({"valid_to"}),
    "manual_task": frozenset({"title", "due_at", "status", "evidence", "version", "updated_by", "updated_at"}),
    "conversation_thread": frozenset({"title", "status", "version", "updated_at", "cleared_at"}),
    "conversation_message": frozenset({"body", "visibility"}),
    "record_revision": frozenset(), "conversation_turn": frozenset(), "conversation_run": frozenset(),
})
VERSIONED_MUTABLE = frozenset({"academic_term", "school_class", "student", "enrollment", "manual_task", "conversation_thread"})
STATES = MappingProxyType({"academic_term": ("active", "archived"), "school_class": ("active", "archived"),
    "student": ("active", "inactive"), "enrollment": ("active", "inactive"),
    "manual_task": ("not-started", "in-progress", "waiting", "done", "cancelled"),
    "conversation_thread": ("active", "archived", "cleared")})


def origin_key(row):
    return row["entity_kind"], row["thread_id"] or "", row["resource_id"], row["source_version"]


def origins_hash(rows):
    return checksum(sorted(rows, key=origin_key))


def source_audit_hash(rows):
    return checksum(sorted(rows, key=lambda row: (row["occurred_at"], row["event_id"])))


def admission_capacity_projection(core, conversations, recovery):
    """Size-only simulation, never emitted as a receipt, witness or permission.

    The committed-stage QG runs this before the source may retire. All future
    anchor hashes/UUIDs have fixed lengths; the immutable pending data cannot
    grow between this observation and admission. No file or SQL is published.
    """
    batch, = recovery["conversation_import"]
    control, = conversations["conversation_control"]
    origins = make_origins(core, conversations, recovery)
    anchor = {"workspace_id": batch["workspace_id"], "attempt_id": batch["attempt_id"],
        "owner_id": batch["restorer_id"], "authority_id": control["authority_id"], "target_binding": batch["target_binding"],
        "retirement_hash": "0" * 64, "retirement_receipt_id": batch["attempt_id"], "stage_hash": "0" * 64,
        "stage_receipt_id": batch["attempt_id"], "target_fence_hash": "0" * 64, "origins_hash": origins_hash(origins),
        "origin_count": len(origins), "batch_hash": checksum(batch),
        "source_audit_hash": source_audit_hash(recovery["conversation_source_audit"]),
        "created_at": _instant(batch["imported_at"]).replace(microsecond=999999).isoformat(),
        "receipt_id": batch["attempt_id"], "proof_hash": "0" * 64}
    return {**recovery, "conversation_admission": [anchor], "conversation_origin": origins}


def _source_row(row, batch):
    original = {**row, "workspace_id": batch["source_workspace_id"]}
    for field in ("created_by", "updated_by", "recorded_by", "owner_id"):
        if field in original:
            if original[field] != batch["restorer_id"]:
                raise ValueError("Imported local FK is not the restorer")
            original[field] = batch["source_owner_id"]
    return original


def identity_hash(kind, original):
    return checksum({key: value for key, value in original.items() if key not in MUTABLE[kind]})


def _resource_key(kind, row):
    return (row.get("thread_id") if kind in ("conversation_turn", "conversation_message", "conversation_run") else None,
            row[ENTITY_KEYS[kind]], row["version"] if kind == "record_revision" else 0)


def _provenance_key(row):
    return row["thread_id"], row["resource_id"], row["source_version"] if row["entity_kind"] == "record_revision" else 0


def _index(core, conversations):
    return {kind: {_resource_key(kind, row): row for row in (core if kind in CORE_COLUMNS else conversations)[kind]}
            for kind in ENTITY_KEYS}


def make_origins(core, conversations, recovery):
    """Called only after exact v4 pending validation, before file publication."""
    batch, = recovery["conversation_import"]
    current = _index(core, conversations)
    result = []
    for provenance in recovery["conversation_provenance"]:
        kind = provenance["entity_kind"]
        row = current[kind][_provenance_key(provenance)]
        original = _source_row(row, batch)
        if checksum(original) != provenance["source_hash"] or row.get("version", 0) != provenance["source_version"]:
            raise ValueError("Only exact pending origins may be admitted")
        result.append({**provenance, "identity_hash": identity_hash(kind, original),
            "body_hash": checksum(original["body"]) if kind == "conversation_message" else None,
            "source_open": kind == "student_identifier" and original["valid_to"] is None,
            "initial_state": original["status"] if kind in STATES else None})
    return sorted(result, key=origin_key)


def validate_origins(rows, provenance, anchor):
    if type(rows) is not list or len(rows) > MAX_ROWS or type(provenance) is not list or len(rows) != len(provenance):
        raise ValueError("Incomplete admission origins")
    if (type(anchor["origin_count"]) is not int or anchor["origin_count"] != len(rows)
            or origins_hash(rows) != anchor["origins_hash"]):
        raise ValueError("Admission origin registry changed")
    projected = []
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != set(ADMISSION_COLUMNS["conversation_origin"]):
            raise ValueError("Unknown admission origin columns")
        kind = row["entity_kind"]
        if kind not in ENTITY_KEYS or origin_key(row) in seen:
            raise ValueError("Unknown or duplicate admission origin")
        seen.add(origin_key(row))
        for field in ("workspace_id", "attempt_id", "resource_id"):
            _uuid(row[field])
        if row["thread_id"] is not None:
            _uuid(row["thread_id"])
        if ((kind in ("conversation_turn", "conversation_message", "conversation_run")) != (row["thread_id"] is not None)
                or type(row["source_version"]) is not int or not 0 <= row["source_version"] <= 2147483647
                or row["workspace_id"] != anchor["workspace_id"] or row["attempt_id"] != anchor["attempt_id"]
                or type(row["source_open"]) is not bool or row["source_open"] and kind != "student_identifier"
                or (row["initial_state"] not in STATES[kind] if kind in STATES else row["initial_state"] is not None)):
            raise ValueError("Invalid origin scope or type")
        _hash(row["identity_hash"])
        _hash(row["source_hash"])
        if kind == "conversation_message":
            _hash(row["body_hash"])
        elif row["body_hash"] is not None:
            raise ValueError("Body digest on a non-message")
        projected.append({key: row[key] for key in IMPORT_COLUMNS["conversation_provenance"]})
    if sorted(projected, key=origin_key) != sorted(provenance, key=origin_key):
        raise ValueError("Original provenance was added, removed or relabeled")


def validate_evolution(core, conversations, recovery, anchor):
    batch, = recovery["conversation_import"]
    origins = recovery["conversation_origin"]
    validate_origins(origins, recovery["conversation_provenance"], anchor)
    current = _index(core, conversations)
    imported = set()
    admitted_at = _instant(anchor["created_at"])
    for origin in origins:
        kind = origin["entity_kind"]
        key = _provenance_key(origin)
        imported.add((kind, key))
        row = current[kind].get(key)
        if row is None:
            raise ValueError("Imported entity/version disappeared")
        original = _source_row(row, batch)
        if identity_hash(kind, original) != origin["identity_hash"]:
            raise ValueError("Imported immutable identity changed")
        version, source_version = row.get("version", 0), origin["source_version"]
        if version < source_version:
            raise ValueError("Imported entity version rolled back")
        previous, state = origin["initial_state"], row.get("status")
        if (previous in ("inactive", "done", "cancelled", "cleared") and state != previous
                or previous == "archived" and state not in ("archived", "cleared")):
            raise ValueError("Imported terminal state reopened")
        if kind == "conversation_message" and row["visibility"] == "restricted":
            # The enclosing v5/v4 projection must independently check the exact
            # current clear marker/thread version/time and every NULL body.
            if row["body"] is not None:
                raise ValueError("Cleared message retained a body")
        elif kind in VERSIONED_MUTABLE and version > source_version:
            if _instant(row["updated_at"]) < admitted_at:
                raise ValueError("Local mutation predates admission")
        elif kind == "student_identifier" and checksum(original) != origin["source_hash"]:
            # Existing BCG allows backdated identifier validity; do not invent
            # a stronger valid_to>=admission restriction. Only close old NULL.
            before = {**original, "valid_to": None}
            if (not origin["source_open"] or original["valid_to"] is None
                    or checksum(before) != origin["source_hash"]):
                raise ValueError("Imported identifier changed beyond closure")
        elif checksum(original) != origin["source_hash"]:
            raise ValueError("Imported immutable content or same-version row changed")
        if kind == "conversation_message" and row["visibility"] == "visible" and checksum(row["body"]) != origin["body_hash"]:
            raise ValueError("Imported visible message body changed")
    for kind, rows in current.items():
        for key, row in rows.items():
            if (kind, key) not in imported:
                created = row["recorded_at"] if kind == "record_revision" else row["created_at"]
                if _instant(created) < admitted_at:
                    raise ValueError("Unattributed local entity predates admission")


@dataclass(frozen=True)
class AdmitConversationTarget:
    attempt_id: UUID
    expected_retirement_hash: str
    expected_stage_hash: str
    expected_origins_hash: str

    def __post_init__(self):
        if type(self.attempt_id) is not UUID:
            raise ValueError("Invalid admission attempt")
        for value in (self.expected_retirement_hash, self.expected_stage_hash, self.expected_origins_hash):
            _hash(value)

    def canonical(self):
        return {"command": "conversation.import.admit", "attempt_id": str(self.attempt_id),
            "expected_retirement_hash": self.expected_retirement_hash, "expected_stage_hash": self.expected_stage_hash,
            "expected_origins_hash": self.expected_origins_hash}


def decode_admission(value):
    if (type(value) is not dict or set(value) != {"command", "attempt_id", "expected_retirement_hash", "expected_stage_hash", "expected_origins_hash"}
            or value["command"] != "conversation.import.admit"):
        raise ValueError("Unregistered admission command")
    result = AdmitConversationTarget(_uuid(value["attempt_id"]), *(value[key] for key in
        ("expected_retirement_hash", "expected_stage_hash", "expected_origins_hash")))
    if result.canonical() != value:
        raise ValueError("Noncanonical admission command")
    return result


@dataclass(frozen=True)
class AdmissionFence:
    retirement: CommittedRetirement
    command: AdmitConversationTarget
    origin_count: int
    batch_hash: str
    source_audit_hash: str
    receipt_id: UUID
    created_at: datetime

    def __post_init__(self):
        _hash(self.batch_hash)
        _hash(self.source_audit_hash)
        if type(self.retirement) is not CommittedRetirement or type(self.command) is not AdmitConversationTarget or type(self.receipt_id) is not UUID:
            raise ValueError("Typed committed retirement required")
        if (type(self.origin_count) is not int or not 0 <= self.origin_count <= MAX_ROWS
                or type(self.created_at) is not datetime or self.created_at.tzinfo is None
                or self.created_at.utcoffset() != timedelta(0) or self.created_at < self.retirement.fence.created_at
                or self.command.attempt_id != self.retirement.fence.command.attempt_id
                or self.command.expected_retirement_hash != self.retirement.proof_hash
                or self.command.expected_stage_hash != self.retirement.fence.stage.snapshot_hash):
            raise ValueError("Admission is not bound to this retirement")

    @property
    def stage(self):
        return self.retirement.fence.stage

    @property
    def workspace_id(self):
        return self.stage.fence.workspace_id

    def canonical(self):
        return {"retirement": {"fence": self.retirement.fence.canonical(), "proof_hash": self.retirement.proof_hash,
                              "receipt_id": str(self.retirement.receipt_id)},
                "command": self.command.canonical(), "origin_count": self.origin_count,
                "batch_hash": self.batch_hash, "source_audit_hash": self.source_audit_hash,
                "receipt_id": str(self.receipt_id), "created_at": self.created_at.isoformat()}

    def anchor(self, proof_hash):
        _hash(proof_hash)
        return {"workspace_id": str(self.workspace_id), "attempt_id": str(self.command.attempt_id),
            "owner_id": str(self.stage.fence.owner_id), "authority_id": str(self.stage.fence.authority_id),
            "target_binding": self.stage.root_binding, "retirement_hash": self.retirement.proof_hash,
            "retirement_receipt_id": str(self.retirement.receipt_id), "stage_hash": self.stage.snapshot_hash,
            "stage_receipt_id": str(self.stage.receipt_id), "target_fence_hash": self.stage.fence_hash,
            "origins_hash": self.command.expected_origins_hash, "origin_count": self.origin_count,
            "batch_hash": self.batch_hash, "source_audit_hash": self.source_audit_hash,
            "created_at": self.created_at.isoformat(), "receipt_id": str(self.receipt_id), "proof_hash": proof_hash}


def decode_admission_fence(value):
    if type(value) is not dict or set(value) != {"retirement", "command", "origin_count", "batch_hash", "source_audit_hash", "receipt_id", "created_at"}:
        raise ValueError("Invalid admission witness fields")
    retirement = value["retirement"]
    if type(retirement) is not dict or set(retirement) != {"fence", "proof_hash", "receipt_id"}:
        raise ValueError("Invalid retirement observation")
    proof = CommittedRetirement(decode_retirement_fence(retirement["fence"]), retirement["proof_hash"], _uuid(retirement["receipt_id"]))
    result = AdmissionFence(proof, decode_admission(value["command"]), value["origin_count"], value["batch_hash"],
                            value["source_audit_hash"], _uuid(value["receipt_id"]), _instant(value["created_at"]))
    if result.canonical() != value:
        raise ValueError("Noncanonical admission witness")
    return result
