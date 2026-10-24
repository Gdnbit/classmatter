"""Closed synthetic v2 evidence package; integrity is NOT recovery authority."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from uuid import UUID
import re

import rfc8785

from .exit_package import (CORE_COLUMNS, AUDIT_COLUMNS, AUDIT_ACTIONS, NULLABLE_AUDIT,
                           MISSING_LIFECYCLE, NONPORTABLE, checksum, validate_package, _validate_column)
from .durable_conversation import ConversationRun, VisibleMessage, ACTIVE_STATES
from .roster import name


SCHEMA = "classmatter.synthetic-exit.v2"
MAX_BYTES = 1048576
MAX_ROWS = 10000
CONVERSATION_COLUMNS = MappingProxyType({
    "conversation_thread": ("workspace_id", "thread_id", "owner_id", "class_id", "term_id", "student_id", "enrollment_id",
                            "title", "status", "version", "created_at", "updated_at", "cleared_at"),
    "conversation_turn": ("workspace_id", "thread_id", "turn_id", "ordinal", "client_request_id", "request_hash", "mode", "draft_kind", "created_at"),
    "conversation_message": ("workspace_id", "thread_id", "turn_id", "message_id", "role", "origin", "visibility", "body", "created_at"),
    "conversation_run": ("workspace_id", "thread_id", "turn_id", "run_id", "state", "version", "created_at", "queued_until",
                         "generation", "started_at", "lease_until", "ended_at", "cancel_requested_at", "input_tokens", "output_tokens", "duration_ms"),
    "conversation_control": ("workspace_id", "owner_id", "authority_id", "epoch", "head_hash", "created_at", "updated_at"),
})
CONVERSATION_KEYS = MappingProxyType({"conversation_thread": ("thread_id",), "conversation_turn": ("thread_id", "ordinal"),
    "conversation_message": ("thread_id", "message_id"), "conversation_run": ("thread_id", "run_id"), "conversation_control": ("workspace_id",)})
NULLABLE = {"conversation_thread": {"student_id", "enrollment_id", "cleared_at"}, "conversation_message": {"body"},
            "conversation_run": {"generation", "started_at", "lease_until", "ended_at", "cancel_requested_at", "input_tokens", "output_tokens", "duration_ms"}}
V2_NONPORTABLE = (*NONPORTABLE, "model-provider-credentials", "source-dpapi-and-root-binding", "run-dispatch-authority", "previous-export-artifacts")
V2_MISSING = (*MISSING_LIFECYCLE, "controlled-import-and-new-identity-admission")
V2_AUDIT_ACTIONS = AUDIT_ACTIONS | {"conversation.history", "exit.conversation.summary", "exit.conversation.download"}


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("Invalid canonical identifier")
    return UUID(value)


def _integer(value, minimum=0, maximum=2147483647):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid bounded integer")


def _instant(value):
    if type(value) is not str:
        raise ValueError("Invalid UTC instant")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(0) or parsed.isoformat() != value:
        raise ValueError("Invalid canonical UTC instant")
    return parsed


def _hash(value):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid content hash")


def snapshot_hash(core, conversations, proof):
    return checksum({"core": core, "conversations": conversations, "restriction_evidence": proof})


@dataclass(frozen=True)
class CreateConversationExit:
    export_id: UUID
    expected_snapshot_hash: str

    def __post_init__(self):
        if type(self.export_id) is not UUID:
            raise ValueError("Invalid export identifier")
        _hash(self.expected_snapshot_hash)

    def canonical(self):
        return {"command": "conversation_exit.create", "export_id": str(self.export_id),
                "expected_snapshot_hash": self.expected_snapshot_hash}


@dataclass(frozen=True)
class ConversationExitSummary:
    snapshot_hash: str
    counts: dict
    restriction_epoch: int


def build_package(workspace, actor, now, core, conversations, proof, audit):
    bundle = {"schema_version": SCHEMA, "purpose": "synthetic-durable-recovery", "source_revision": "0019",
              "workspace_id": str(workspace), "actor_refs": [str(actor)], "created_at": now.isoformat(),
              "core": core, "conversations": conversations, "restriction_evidence": proof,
              "snapshot_hash": snapshot_hash(core, conversations, proof), "audit_refs": audit,
              "activation_allowed": False, "run_authority": "source-evidence-only",
              "nonportable": list(V2_NONPORTABLE), "lifecycle_status": {"complete": False, "missing": list(V2_MISSING)}}
    bundle["package_checksum"] = checksum(bundle)
    validate_v2(bundle)
    return bundle


def validate_v2(bundle, *, require_complete=False):
    try:
        return _validate(bundle, require_complete)
    except Exception:
        raise ValueError("Invalid or incomplete synthetic conversation exit; no recovery authority") from None


def _validate(bundle, require_complete):
    fields = {"schema_version", "purpose", "source_revision", "workspace_id", "actor_refs", "created_at", "core", "conversations",
              "restriction_evidence", "snapshot_hash", "audit_refs", "activation_allowed", "run_authority", "nonportable",
              "lifecycle_status", "package_checksum"}
    if type(bundle) is not dict or set(bundle) != fields or require_complete:
        raise ValueError()
    if (bundle["schema_version"] != SCHEMA or bundle["purpose"] != "synthetic-durable-recovery" or bundle["source_revision"] != "0019"
            or bundle["activation_allowed"] is not False or bundle["run_authority"] != "source-evidence-only"
            or bundle["nonportable"] != list(V2_NONPORTABLE)
            or type(bundle["lifecycle_status"]) is not dict or bundle["lifecycle_status"].get("complete") is not False
            or bundle["lifecycle_status"] != {"complete": False, "missing": list(V2_MISSING)}):
        raise ValueError()
    _uuid(bundle["workspace_id"])
    at = _instant(bundle["created_at"])
    if type(bundle["actor_refs"]) is not list or len(bundle["actor_refs"]) != 1:
        raise ValueError()
    actor = bundle["actor_refs"][0]
    _uuid(actor)
    # Reuse the unchanged v1 core validator through a private projection. This
    # is not an emitted v1 artifact, and does not relax its audit/action profile.
    legacy = {"schema_version": "class-os.synthetic-core-exit.v1", "purpose": "synthetic-core-recovery",
              "workspace_id": bundle["workspace_id"], "actor_refs": [actor], "created_at": bundle["created_at"],
              "core": bundle["core"], "core_checksum": checksum(bundle["core"]), "nonportable": list(NONPORTABLE),
              "lifecycle_status": {"complete": False, "missing": list(MISSING_LIFECYCLE)}, "audit_refs": []}
    legacy["package_checksum"] = checksum(legacy)
    counts = validate_package(legacy)
    collections = bundle["conversations"]
    if type(collections) is not dict or set(collections) != set(CONVERSATION_COLUMNS):
        raise ValueError()
    for table, columns in CONVERSATION_COLUMNS.items():
        rows = collections[table]
        if type(rows) is not list or len(rows) > MAX_ROWS:
            raise ValueError()
        counts[table] = len(rows)
        for row in rows:
            if type(row) is not dict or set(row) != set(columns) or row["workspace_id"] != bundle["workspace_id"]:
                raise ValueError()
            for key, value in row.items():
                if value is None and key not in NULLABLE.get(table, ()):
                    raise ValueError()
                if key.endswith("_id") and value is not None:
                    _uuid(value)
                if key.endswith("_at") or key in ("lease_until", "queued_until"):
                    if value is not None and _instant(value) > at:
                        if key not in ("lease_until", "queued_until"):
                            raise ValueError()
            if "version" in row:
                _integer(row["version"], 1)
    proof = bundle["restriction_evidence"]
    if type(proof) is not dict or set(proof) != {"authority_id", "epoch", "source_head_hash", "markers"}:
        raise ValueError()
    _uuid(proof["authority_id"])
    _integer(proof["epoch"], maximum=4096)
    _hash(proof["source_head_hash"])
    if type(proof["markers"]) is not list or len(proof["markers"]) != proof["epoch"]:
        raise ValueError()
    markers, last = {}, None
    for row in proof["markers"]:
        if type(row) is not dict or set(row) != {"thread_id", "version_after", "restricted_at"}:
            raise ValueError()
        _uuid(row["thread_id"])
        _integer(row["version_after"], 2)
        time = _instant(row["restricted_at"])
        if row["thread_id"] in markers or time > at or last is not None and time < last:
            raise ValueError()
        markers[row["thread_id"]], last = row, time
    controls = collections["conversation_control"]
    if len(controls) != 1:
        raise ValueError()
    control = controls[0]
    _integer(control["epoch"], maximum=4096)
    if (control["owner_id"] != actor or control["authority_id"] != proof["authority_id"] or control["epoch"] != proof["epoch"]
            or control["head_hash"] != proof["source_head_hash"] or _instant(control["updated_at"]) < _instant(control["created_at"])):
        raise ValueError()
    classes = {(row["class_id"], row["term_id"]) for row in bundle["core"]["school_class"]}
    enrollments = {(r["student_id"], r["class_id"], r["term_id"], r["enrollment_id"]) for r in bundle["core"]["enrollment"]}
    threads, turns, slots, request_keys, ordinals, run_ids, message_ids, active = {}, {}, {}, set(), set(), set(), set(), set()
    sequences = {}
    for row in collections["conversation_thread"]:
        key = row["thread_id"]
        name(row["title"])
        if (key in threads or row["owner_id"] != actor or (row["class_id"], row["term_id"]) not in classes
                or row["status"] not in ("active", "archived", "cleared")
                or _instant(row["updated_at"]) < _instant(row["created_at"])
                or (row["student_id"] is None) != (row["enrollment_id"] is None)
                or row["student_id"] is not None and (row["student_id"], row["class_id"], row["term_id"], row["enrollment_id"]) not in enrollments):
            raise ValueError()
        marker = markers.get(key)
        if row["status"] == "cleared":
            if (not marker or row["title"] != "已清除的会话" or row["cleared_at"] != marker["restricted_at"]
                    or row["version"] != marker["version_after"]
                    or not _instant(row["created_at"]) <= _instant(row["cleared_at"]) <= _instant(row["updated_at"])):
                raise ValueError()
        elif marker is not None or row["cleared_at"] is not None:
            raise ValueError()
        threads[key] = row
    # Current D1 retains cleared thread rows; an orphan marker indicates an
    # incomplete snapshot, not an independently portable tombstone.
    if not markers.keys() <= threads.keys():
        raise ValueError()
    for row in collections["conversation_turn"]:
        key = row["thread_id"], row["turn_id"]
        _integer(row["ordinal"], 1, 10000)
        _hash(row["request_hash"])
        request, ordinal = (row["thread_id"], row["client_request_id"]), (row["thread_id"], row["ordinal"])
        if (key in turns or row["thread_id"] not in threads or request in request_keys or ordinal in ordinals
                or row["mode"] not in ("read", "draft", "chat") or row["draft_kind"] not in ("task", "record-note")):
            raise ValueError()
        if _instant(row["created_at"]) < _instant(threads[row["thread_id"]]["created_at"]):
            raise ValueError()
        turns[key] = row
        request_keys.add(request)
        ordinals.add(ordinal)
        sequences.setdefault(row["thread_id"], []).append(row["ordinal"])
        slots[key] = {}
    for values in sequences.values():
        values = sorted(values)
        if values != list(range(1, len(values) + 1)):
            raise ValueError()
    for row in collections["conversation_message"]:
        key, ident = (row["thread_id"], row["turn_id"]), (row["thread_id"], row["message_id"])
        if key not in turns or ident in message_ids or row["role"] in slots[key]:
            raise ValueError()
        if _instant(row["created_at"]) < _instant(turns[key]["created_at"]):
            raise ValueError()
        if (row["role"], row["origin"]) not in (("user", "user-original"), ("assistant", "assistant-unverified")):
            raise ValueError()
        if threads[row["thread_id"]]["status"] == "cleared":
            if row["visibility"] != "restricted" or row["body"] is not None:
                raise ValueError()
        else:
            if row["visibility"] != "visible":
                raise ValueError()
            VisibleMessage(row["role"], row["origin"], row["body"])
            if row["role"] == "user" and len(row["body"]) > 2000:
                raise ValueError()
        slots[key][row["role"]] = row
        message_ids.add(ident)
    run_turns = set()
    for row in collections["conversation_run"]:
        key, ident = (row["thread_id"], row["turn_id"]), (row["thread_id"], row["run_id"])
        if key not in turns or key in run_turns or ident in run_ids:
            raise ValueError()
        times = {key: _instant(row[key]) if row[key] is not None else None
                 for key in ("started_at", "lease_until", "ended_at", "cancel_requested_at")}
        ConversationRun(_uuid(row["run_id"]), row["state"], row["version"],
                        _uuid(row["generation"]) if row["generation"] is not None else None, **times)
        created, until = _instant(row["created_at"]), _instant(row["queued_until"])
        if (created < _instant(turns[key]["created_at"]) or not timedelta(0) < until - created <= timedelta(minutes=5)
                or times["started_at"] is not None and not created <= times["started_at"] < until
                or row["state"] == "cancelled" and times["started_at"] is None and times["ended_at"] < created
                or "user" not in slots[key] or ("assistant" in slots[key]) != (row["state"] == "completed")):
            raise ValueError()
        for field in ("input_tokens", "output_tokens", "duration_ms"):
            if row[field] is not None:
                _integer(row[field])
                if row["state"] in ACTIVE_STATES:
                    raise ValueError()
        if row["state"] in ACTIVE_STATES:
            if row["thread_id"] in active or threads[row["thread_id"]]["status"] != "active":
                raise ValueError()
            active.add(row["thread_id"])
        run_turns.add(key)
        run_ids.add(ident)
    if run_turns != set(turns):
        raise ValueError()
    audit = bundle["audit_refs"]
    if type(audit) is not list or len(audit) > MAX_ROWS:
        raise ValueError()
    seen = set()
    for row in audit:
        if (type(row) is not dict or set(row) != set(AUDIT_COLUMNS) or row["workspace_id"] != bundle["workspace_id"]
                or row["actor_id"] != actor or row["event_id"] in seen or row["action"] not in V2_AUDIT_ACTIONS
                or row["purpose"] not in ("manage-roster", "manage-class", "manage-conversation", "exit-recovery", "manage-model")
                or row["outcome"] not in ("allowed", "denied")):
            raise ValueError()
        for field, value in row.items():
            _validate_column(field, value, nullable=field in NULLABLE_AUDIT)
        if _instant(row["occurred_at"]) > at:
            raise ValueError()
        seen.add(row["event_id"])
    _hash(bundle["snapshot_hash"])
    _hash(bundle["package_checksum"])
    if (bundle["snapshot_hash"] != snapshot_hash(bundle["core"], collections, proof)
            or bundle["package_checksum"] != checksum({key: value for key, value in bundle.items() if key != "package_checksum"})
            or len(rfc8785.dumps(bundle)) > MAX_BYTES):
        raise ValueError()
    return counts
