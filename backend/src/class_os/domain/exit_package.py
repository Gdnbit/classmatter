"""Versioned synthetic core exit format, not a universal entity/fact store.

This slice cannot claim lifecycle-complete or production-retirement proof.
"""
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import re
from types import MappingProxyType
from uuid import UUID

import rfc8785


COMMON = ("version", "created_by", "updated_by", "created_at", "updated_at")
CORE_COLUMNS = MappingProxyType({
    "workspace": ("workspace_id", "data_mode", "created_at"),
    "academic_term": ("workspace_id", "term_id", "name", "start_date", "end_date", "status", *COMMON),
    "school_class": ("workspace_id", "class_id", "term_id", "name", "status", *COMMON),
    "student": ("workspace_id", "student_id", "name", "status", *COMMON),
    "enrollment": ("workspace_id", "enrollment_id", "student_id", "class_id", "term_id", "valid_from", "valid_to", "status", *COMMON),
    "student_identifier": ("workspace_id", "identifier_id", "student_id", "authority", "identifier_type", "value", "valid_from", "valid_to", "created_by", "created_at"),
    "record_revision": ("workspace_id", "record_id", "version", "class_id", "term_id", "student_id", "kind", "occurred_at", "recorded_at", "recorded_by", "fact_text", "observation_text", "source", "related_record_id", "revision_kind", "revision_reason"),
    "manual_task": ("workspace_id", "task_id", "class_id", "term_id", "title", "student_id", "source_record_id", "due_at", "status", "evidence", *COMMON),
})
NONPORTABLE = ("passwords-and-recovery-codes", "sessions-and-approval-capabilities", "sdk-conversation-memory", "database-credentials")
MISSING_LIFECYCLE = ("rights-request-ledger", "restriction-ledger", "delete-ledger", "retention-ledger", "admission-ledger", "retirement-proof")
PRIMARY_KEYS = MappingProxyType({"workspace": ("workspace_id",), "academic_term": ("term_id",),
    "school_class": ("class_id",), "student": ("student_id",), "enrollment": ("enrollment_id",),
    "student_identifier": ("identifier_id",), "record_revision": ("record_id", "version"), "manual_task": ("task_id",)})
AUDIT_COLUMNS = ("workspace_id", "event_id", "actor_id", "purpose", "action", "outcome", "occurred_at", "proposal_id",
                 "payload_hash", "receipt_id", "resource_id", "resource_version", "class_id", "term_id")
NULLABLE_CORE = MappingProxyType({
    "enrollment": frozenset({"valid_to"}), "student_identifier": frozenset({"valid_to"}),
    "record_revision": frozenset({"related_record_id"}),
    "manual_task": frozenset({"student_id", "source_record_id", "due_at"}),
})
NULLABLE_AUDIT = frozenset({"proposal_id", "payload_hash", "receipt_id", "resource_id", "resource_version", "class_id", "term_id"})
AUDIT_ACTIONS = frozenset({"command.preview", "command.approve", "command.reject", "command.commit", "command.status",
    "roster.list", "class.context", "class.history", "identifier.list", "duplicate.list", "activity.today", "student.timeline",
    "agent.run.started", "agent.run.completed", "agent.run.failed", "agent.run.cancelled", "exit.summary", "exit.download", "audit.list",
    "model.config.read", "model.test.started", "model.test.completed", "model.test.failed", "model.enable", "model.disable", "model.invoke"})


def _validate_column(field, value, *, nullable=False):
    """Scalar types of this fixed exit format; not a custom-schema facility."""
    if value is None:
        if nullable:
            return
        raise ValueError("Missing required exit value")
    if field in ("version", "resource_version"):
        if type(value) is not int or not 1 <= value <= 2147483647:
            raise ValueError("Invalid PostgreSQL resource version")
        return
    if type(value) is not str:
        raise ValueError("Invalid exit scalar type")
    if field.endswith("_id") or field in ("created_by", "updated_by", "recorded_by"):
        if str(UUID(value)) != value:
            raise ValueError("Invalid canonical exit identifier")
    elif field.endswith("_at") or field in ("valid_from", "valid_to"):
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None or parsed.isoformat() != value:
            raise ValueError("Ambiguous exit timestamp")
    elif field in ("start_date", "end_date"):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Invalid canonical exit date")
    elif field == "payload_hash" and not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid audit payload hash")


def checksum(value):
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


@dataclass(frozen=True)
class CreateExitExport:
    export_id: UUID
    expected_core_hash: str

    def __post_init__(self):
        if type(self.export_id) is not UUID or not isinstance(self.expected_core_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", self.expected_core_hash):
            raise ValueError("Invalid exit export")

    def canonical(self):
        return {"command": "exit_export.create", "export_id": str(self.export_id), "expected_core_hash": self.expected_core_hash}


@dataclass(frozen=True)
class ExitSummary:
    core_hash: str
    counts: dict


@dataclass(frozen=True)
class ExitArtifact:
    export_id: UUID
    package_hash: str
    bundle: dict


def validate_package(bundle, *, require_complete=False):
    fields = {"schema_version", "purpose", "workspace_id", "created_at", "actor_refs", "core", "core_checksum",
              "package_checksum", "nonportable", "lifecycle_status", "audit_refs"}
    if type(bundle) is not dict or set(bundle) != fields:
        raise ValueError("Unknown exit package fields")
    lifecycle = bundle["lifecycle_status"]
    if (type(lifecycle) is not dict or set(lifecycle) != {"complete", "missing"}
            or type(lifecycle["complete"]) is not bool or lifecycle["complete"] is not False):
        raise ValueError("Invalid lifecycle status type")
    if (bundle["schema_version"] != "class-os.synthetic-core-exit.v1" or bundle["purpose"] != "synthetic-core-recovery"
            or bundle["nonportable"] != list(NONPORTABLE)
            or bundle["lifecycle_status"] != {"complete": False, "missing": list(MISSING_LIFECYCLE)}):
        raise ValueError("Unsupported exit package profile")
    if require_complete:
        raise ValueError("Lifecycle ledgers/retirement proof not implemented; core exit is not a release proof")
    _validate_column("workspace_id", bundle["workspace_id"])
    _validate_column("created_at", bundle["created_at"])
    if type(bundle["actor_refs"]) is not list or len(bundle["actor_refs"]) != 1:
        raise ValueError("Invalid owner mapping")
    for actor in bundle["actor_refs"]:
        _validate_column("actor_id", actor)
    actors = set(bundle["actor_refs"])
    core = bundle["core"]
    if type(core) is not dict or set(core) != set(CORE_COLUMNS):
        raise ValueError("Unknown core collection")
    if checksum(core) != bundle["core_checksum"] or checksum({key: value for key, value in bundle.items() if key != "package_checksum"}) != bundle["package_checksum"]:
        raise ValueError("Exit package checksum mismatch")
    counts = {}
    seen = {table: set() for table in CORE_COLUMNS}
    for table, columns in CORE_COLUMNS.items():
        rows = core[table]
        if type(rows) is not list or len(rows) > 10000:
            raise ValueError("Invalid core collection size")
        counts[table] = len(rows)
        for row in rows:
            if type(row) is not dict or set(row) != set(columns) or row["workspace_id"] != bundle["workspace_id"]:
                raise ValueError("Invalid core row or scope")
            for field, value in row.items():
                _validate_column(field, value, nullable=field in NULLABLE_CORE.get(table, ()))
                if field in ("created_by", "updated_by", "recorded_by") and value not in actors:
                    raise ValueError("Unresolved actor reference")
            key = tuple(row[field] for field in PRIMARY_KEYS[table])
            if key in seen[table]:
                raise ValueError("Duplicate core entity")
            seen[table].add(key)
    if counts["workspace"] != 1 or core["workspace"][0]["data_mode"] != "synthetic-only":
        raise ValueError("Exit contains non-synthetic or missing workspace")
    terms = {row["term_id"] for row in core["academic_term"]}
    classes = {(row["class_id"], row["term_id"]) for row in core["school_class"]}
    students = {row["student_id"] for row in core["student"]}
    records = {row["record_id"]: (row["student_id"], row["class_id"], row["term_id"]) for row in core["record_revision"]}
    record_relations = {row["record_id"]: (row["kind"], row["occurred_at"], row["related_record_id"]) for row in core["record_revision"]}
    from .activity import CreateRecord, LEAVE_PREDECESSORS
    for row in core["academic_term"]:
        if date.fromisoformat(row["start_date"]) >= date.fromisoformat(row["end_date"]):
            raise ValueError("Invalid term interval")
    for table, rows in core.items():
        for row in rows:
            from .roster import name
            if "name" in row:
                name(row["name"])
            if table == "manual_task":
                from .activity import content
                name(row["title"])
                content(row["evidence"], maximum=500)
                if row["status"] in ("done", "cancelled") and not row["evidence"].strip():
                    raise ValueError("Missing task outcome evidence")
            statuses = {"academic_term": ("active", "archived"), "school_class": ("active", "archived"),
                        "student": ("active", "inactive"), "enrollment": ("active", "inactive"),
                        "manual_task": ("not-started", "in-progress", "waiting", "done", "cancelled")}
            if table in statuses and row["status"] not in statuses[table]:
                raise ValueError("Unknown core state")
            if table == "record_revision":
                from .activity import content
                if row["source"] != "trusted-ui-synthetic" or row["revision_kind"] not in ("create", "correct", "supersede"):
                    raise ValueError("Unknown record kind/source")
                CreateRecord("record.create", UUID(row["record_id"]), UUID(row["class_id"]), UUID(row["term_id"]),
                             UUID(row["student_id"]), row["kind"], datetime.fromisoformat(row["occurred_at"]),
                             row["fact_text"], row["observation_text"],
                             UUID(row["related_record_id"]) if row["related_record_id"] is not None else None)
                content(row["revision_reason"], maximum=500, required=row["version"] > 1)
                if row["version"] == 1 and row["revision_reason"]:
                    raise ValueError("Unexpected creation revision reason")
                if (row["version"] == 1 and row["revision_kind"] != "create") or (row["version"] > 1 and (row["revision_kind"] == "create" or not row["revision_reason"].strip())):
                    raise ValueError("Invalid revision provenance")
                if datetime.fromisoformat(row["occurred_at"]) > datetime.fromisoformat(row["recorded_at"]):
                    raise ValueError("Record precedes its occurrence")
            if table == "student_identifier":
                name(row["authority"])
                name(row["value"])
                if row["identifier_type"] not in ("school_number", "exam_number"):
                    raise ValueError("Unknown identifier type")
            if "term_id" in row and row["term_id"] not in terms:
                raise ValueError("Unresolved term")
            if "class_id" in row and (row["class_id"], row["term_id"]) not in classes:
                raise ValueError("Unresolved class/term")
            if "student_id" in row and row["student_id"] is not None and row["student_id"] not in students:
                raise ValueError("Unresolved student")
            if "valid_from" in row and row["valid_to"] and datetime.fromisoformat(row["valid_from"]) >= datetime.fromisoformat(row["valid_to"]):
                raise ValueError("Invalid validity interval")
            for field in ("related_record_id", "source_record_id"):
                if field in row and row[field] is not None:
                    target = records.get(row[field])
                    if not target or target[1:] != (row["class_id"], row["term_id"]) or (row.get("student_id") is not None and target[0] != row["student_id"]):
                        raise ValueError("Unresolved record reference")
                    if field == "related_record_id" and row["kind"] in LEAVE_PREDECESSORS:
                        previous_kind, previous_time, _ = record_relations[row[field]]
                        if previous_kind != LEAVE_PREDECESSORS[row["kind"]] or datetime.fromisoformat(previous_time) > datetime.fromisoformat(row["occurred_at"]):
                            raise ValueError("Invalid leave predecessor")
    revisions = {}
    immutable_record = {}
    for row in core["record_revision"]:
        revisions.setdefault(row["record_id"], []).append(row["version"])
        source = tuple(row[field] for field in ("student_id", "class_id", "term_id", "kind", "occurred_at", "source", "related_record_id"))
        if row["record_id"] in immutable_record and immutable_record[row["record_id"]] != source:
            raise ValueError("Record revision changed immutable identity/source")
        immutable_record[row["record_id"]] = source
    if any(sorted(values) != list(range(1, len(values) + 1)) for values in revisions.values()):
        raise ValueError("Missing record history revision")
    # BCG creation can only reference an existing Record, and later revisions
    # cannot change that link. Iterate to keep long valid chains off the stack.
    visited = set()
    for cursor in record_relations:
        path = set()
        while cursor is not None and cursor not in visited:
            if cursor in path:
                raise ValueError("Cyclic record reference")
            path.add(cursor)
            cursor = record_relations[cursor][2]
        visited.update(path)
    if type(bundle["audit_refs"]) is not list or len(bundle["audit_refs"]) > 10000:
        raise ValueError("Invalid audit reference collection")
    audit_ids = set()
    for row in bundle["audit_refs"]:
        if type(row) is not dict or set(row) != set(AUDIT_COLUMNS) or row["workspace_id"] != bundle["workspace_id"] or row["actor_id"] not in actors:
            raise ValueError("Invalid audit reference scope")
        for field in AUDIT_COLUMNS:
            _validate_column(field, row[field], nullable=field in NULLABLE_AUDIT)
        if row["purpose"] not in ("manage-roster", "manage-class", "exit-recovery", "manage-model") or row["action"] not in AUDIT_ACTIONS:
            raise ValueError("Unknown audit purpose/action")
        if row["event_id"] in audit_ids or row["outcome"] not in ("allowed", "denied") or datetime.fromisoformat(row["occurred_at"]).utcoffset() is None:
            raise ValueError("Invalid audit reference")
        audit_ids.add(row["event_id"])
    return counts
