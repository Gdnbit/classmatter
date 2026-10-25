"""Closed recovery provenance format; still not target admission authority."""
from copy import deepcopy

import rfc8785

from .conversation_exit import MAX_BYTES, MAX_ROWS, AUDIT_COLUMNS, V2_AUDIT_ACTIONS, _uuid, _hash, _instant
from .conversation_exit_v3 import CONVERSATION_COLUMNS, build_package as build_v3, validate_v3
from .exit_package import checksum, _validate_column, NULLABLE_AUDIT
from .target_import import IMPORT_COLUMNS, ENTITY_KEYS, provenance_rows


SCHEMA = "classmatter.synthetic-exit.v4"
V4_AUDIT_ACTIONS = V2_AUDIT_ACTIONS | {"conversation.transfer.proof"}


def validate_audit(rows, workspace, actor, at):
    if type(rows) is not list or len(rows) > MAX_ROWS:
        raise ValueError("Invalid v4 audit collection")
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != set(AUDIT_COLUMNS):
            raise ValueError("Invalid v4 audit columns")
        for key in AUDIT_COLUMNS:
            _validate_column(key, row[key], nullable=key in NULLABLE_AUDIT)
        if (row["workspace_id"] != workspace or row["actor_id"] != actor or row["event_id"] in seen
                or row["action"] not in V4_AUDIT_ACTIONS or row["outcome"] not in ("allowed", "denied")
                or row["purpose"] not in ("manage-roster", "manage-class", "exit-recovery", "manage-model", "manage-conversation")
                or row["action"] == "conversation.transfer.proof" and row["purpose"] != "exit-recovery"
                or _instant(row["occurred_at"]) > at):
            raise ValueError("Invalid v4 audit scope or action")
        seen.add(row["event_id"])


def snapshot_hash(core, conversations, proof, recovery):
    return checksum({"core": core, "conversations": conversations, "restriction_evidence": proof, "recovery": recovery})


def build_package(workspace, actor, now, core, conversations, proof, audit, recovery):
    validate_audit(audit, str(workspace), str(actor), now)
    # Private legacy projection only. The emitted v4 retains EVERY audit row,
    # including new actions which must not broaden v2/v3's fixed contract.
    legacy_audit = [row for row in audit if row["action"] in V2_AUDIT_ACTIONS]
    bundle = build_v3(workspace, actor, now, core, conversations, proof, legacy_audit)
    bundle.update(schema_version=SCHEMA, source_revision="0021", recovery=recovery, audit_refs=audit,
                  snapshot_hash=snapshot_hash(core, conversations, proof, recovery))
    bundle["package_checksum"] = checksum({k: v for k, v in bundle.items() if k != "package_checksum"})
    validate_v4(bundle)
    return bundle


def validate_v4(bundle, *, require_complete=False):
    try:
        return _validate(bundle, require_complete)
    except Exception:
        raise ValueError("Invalid synthetic v4 provenance; no target admission") from None


def _validate(bundle, require_complete):
    if (type(bundle) is not dict or bundle.get("schema_version") != SCHEMA or bundle.get("source_revision") != "0021"
            or len(rfc8785.dumps(bundle)) > MAX_BYTES
            or bundle["package_checksum"] != checksum({k: v for k, v in bundle.items() if k != "package_checksum"})
            or bundle["snapshot_hash"] != snapshot_hash(bundle["core"], bundle["conversations"], bundle["restriction_evidence"], bundle["recovery"])):
        raise ValueError()
    projected = deepcopy(bundle)
    recovery = projected.pop("recovery")
    validate_audit(bundle["audit_refs"], bundle["workspace_id"], bundle["actor_refs"][0], _instant(bundle["created_at"]))
    projected["audit_refs"] = [row for row in bundle["audit_refs"] if row["action"] in V2_AUDIT_ACTIONS]
    projected.update(schema_version="classmatter.synthetic-exit.v3", source_revision="0020")
    from .conversation_exit import snapshot_hash as old_hash
    projected["snapshot_hash"] = old_hash(projected["core"], projected["conversations"], projected["restriction_evidence"])
    projected["package_checksum"] = checksum({k: v for k, v in projected.items() if k != "package_checksum"})
    counts = validate_v3(projected, require_complete=require_complete)
    if type(recovery) is not dict or set(recovery) != set(IMPORT_COLUMNS):
        raise ValueError()
    for table, columns in IMPORT_COLUMNS.items():
        rows = recovery[table]
        if type(rows) is not list or len(rows) > MAX_ROWS:
            raise ValueError()
        counts[table] = len(rows)
        for row in rows:
            if type(row) is not dict or set(row) != set(columns) or row["workspace_id"] != bundle["workspace_id"]:
                raise ValueError()
    batches, origins, audit = (recovery[k] for k in IMPORT_COLUMNS)
    if not batches:
        if origins or audit:
            raise ValueError()
        return counts
    if len(batches) != 1:
        raise ValueError()
    batch = batches[0]
    for key in ("workspace_id", "attempt_id", "restorer_id", "source_workspace_id", "source_owner_id", "source_authority_id", "source_receipt_id"):
        _uuid(batch[key])
    for key in ("source_head_hash", "source_fence_hash", "source_root_binding", "package_hash", "target_binding"):
        _hash(batch[key])
    if (batch["restorer_id"] != bundle["actor_refs"][0] or batch["source_workspace_id"] == bundle["workspace_id"]
            or batch["source_owner_id"] == batch["restorer_id"] or batch["source_root_binding"] == batch["target_binding"]
            or type(batch["source_epoch"]) is not int or not 0 <= batch["source_epoch"] <= 4096 or batch["phase"] != "pending"
            or not _instant(batch["source_sealed_at"]) <= _instant(batch["imported_at"]) <= _instant(bundle["created_at"])):
        raise ValueError()
    # Pending targets have no local edits. Reconstruct each exact source row
    # before checking its hash; restorer is never silently asserted as author.
    original = deepcopy(bundle)
    for kind in ENTITY_KEYS:
        for row in original["core" if kind in original["core"] else "conversations"][kind]:
            row["workspace_id"] = batch["source_workspace_id"]
            for field in ("created_by", "updated_by", "recorded_by", "owner_id"):
                if field in row:
                    if row[field] != batch["restorer_id"]:
                        raise ValueError()
                    row[field] = batch["source_owner_id"]
    expected = provenance_rows(original, _uuid(bundle["workspace_id"]), _uuid(batch["attempt_id"]))
    for row in origins:
        if type(row["source_version"]) is not int or not 0 <= row["source_version"] <= 2147483647:
            raise ValueError()
        _hash(row["source_hash"])
        _uuid(row["attempt_id"])
        _uuid(row["resource_id"])
        if row["thread_id"] is not None:
            _uuid(row["thread_id"])
    ordering = lambda r: (r["entity_kind"], r["thread_id"] or "", r["resource_id"], r["source_version"])
    if sorted(origins, key=ordering) != sorted(expected, key=ordering):
        raise ValueError()
    if any(r["state"] in {"queued", "running", "cancel_requested"} for r in bundle["conversations"]["conversation_run"]):
        raise ValueError()
    if batch["source_epoch"] != bundle["restriction_evidence"]["epoch"]:
        raise ValueError()
    for row in audit:
        if row["attempt_id"] != batch["attempt_id"] or row["source_workspace_id"] != batch["source_workspace_id"]:
            raise ValueError()
    normalized = [{**{key: row[key] for key in AUDIT_COLUMNS}, "workspace_id": row["source_workspace_id"]} for row in audit]
    validate_audit(normalized, batch["source_workspace_id"], batch["source_owner_id"], _instant(batch["source_sealed_at"]))
    return counts
