"""Fixed editable recovery evidence. Offline integrity never activates a target."""
from copy import deepcopy

import rfc8785

from .conversation_exit import MAX_BYTES, MAX_ROWS, _uuid, _hash, _instant
from .conversation_exit_v4 import build_package as build_v4, validate_v4, snapshot_hash, validate_audit
from .exit_package import checksum
from .target_import import IMPORT_COLUMNS
from .recovery_admission import ADMISSION_COLUMNS, RECOVERY_COLUMNS, validate_evolution, source_audit_hash


SCHEMA = "classmatter.synthetic-exit.v5"


def _legacy_recovery(recovery):
    admitted = bool(recovery.get("conversation_admission"))
    return {key: [] if admitted else recovery[key] for key in IMPORT_COLUMNS}


def build_package(workspace, actor, now, core, conversations, proof, audit, recovery):
    bundle = build_v4(workspace, actor, now, core, conversations, proof, audit, _legacy_recovery(recovery))
    bundle.update(schema_version=SCHEMA, source_revision="0023", recovery=recovery,
                  snapshot_hash=snapshot_hash(core, conversations, proof, recovery))
    bundle["package_checksum"] = checksum({key: value for key, value in bundle.items() if key != "package_checksum"})
    validate_v5(bundle)
    return bundle


def validate_v5(bundle, *, require_complete=False):
    try:
        return _validate(bundle, require_complete)
    except Exception:
        raise ValueError("Invalid synthetic v5 evolution; no offline activation") from None


def _validate(bundle, require_complete):
    if (type(bundle) is not dict or bundle.get("schema_version") != SCHEMA or bundle.get("source_revision") != "0023"
            or len(rfc8785.dumps(bundle)) > MAX_BYTES
            or bundle["package_checksum"] != checksum({key: value for key, value in bundle.items() if key != "package_checksum"})
            or bundle["snapshot_hash"] != snapshot_hash(bundle["core"], bundle["conversations"], bundle["restriction_evidence"], bundle["recovery"])):
        raise ValueError()
    recovery = bundle["recovery"]
    if type(recovery) is not dict or set(recovery) != set(RECOVERY_COLUMNS):
        raise ValueError()
    for kind, columns in RECOVERY_COLUMNS.items():
        rows = recovery[kind]
        if type(rows) is not list or len(rows) > MAX_ROWS:
            raise ValueError()
        for row in rows:
            if type(row) is not dict or set(row) != set(columns) or row["workspace_id"] != bundle["workspace_id"]:
                raise ValueError()
    # V4 remains byte-for-byte its exact pending semantics. The private native
    # projection only supplies its established core/conversation/audit checks;
    # it is never emitted or accepted as provenance for edited imported data.
    projected = deepcopy(bundle)
    projected.update(schema_version="classmatter.synthetic-exit.v4", source_revision="0021", recovery=_legacy_recovery(recovery))
    projected["snapshot_hash"] = snapshot_hash(projected["core"], projected["conversations"], projected["restriction_evidence"], projected["recovery"])
    projected["package_checksum"] = checksum({key: value for key, value in projected.items() if key != "package_checksum"})
    counts = validate_v4(projected, require_complete=require_complete)
    counts.update({kind: len(rows) for kind, rows in recovery.items()})
    anchors, origins = (recovery[key] for key in ADMISSION_COLUMNS)
    if not anchors:
        if origins:
            raise ValueError()
        return counts
    if len(anchors) != 1 or len(recovery["conversation_import"]) != 1:
        raise ValueError()
    anchor, batch = anchors[0], recovery["conversation_import"][0]
    for key in ("workspace_id", "attempt_id", "owner_id", "authority_id", "retirement_receipt_id", "stage_receipt_id", "receipt_id"):
        _uuid(anchor[key])
    for key in ("target_binding", "retirement_hash", "stage_hash", "target_fence_hash", "origins_hash", "batch_hash", "source_audit_hash", "proof_hash"):
        _hash(anchor[key])
    for key in ("workspace_id", "attempt_id", "restorer_id", "source_workspace_id", "source_owner_id", "source_authority_id", "source_receipt_id"):
        _uuid(batch[key])
    for key in ("source_head_hash", "source_fence_hash", "source_root_binding", "package_hash", "target_binding"):
        _hash(batch[key])
    control, = bundle["conversations"]["conversation_control"]
    if (anchor["batch_hash"] != checksum(batch)
            or anchor["source_audit_hash"] != source_audit_hash(recovery["conversation_source_audit"])):
        raise ValueError()
    if (batch["phase"] != "pending" or batch["attempt_id"] != anchor["attempt_id"]
            or batch["restorer_id"] != bundle["actor_refs"][0] or anchor["owner_id"] != batch["restorer_id"]
            or batch["source_owner_id"] == batch["restorer_id"] or batch["source_workspace_id"] == bundle["workspace_id"]
            or batch["target_binding"] != anchor["target_binding"] or batch["source_root_binding"] == batch["target_binding"]
            or anchor["authority_id"] != control["authority_id"] or control["transfer_id"] is not None
            or type(batch["source_epoch"]) is not int or not 0 <= batch["source_epoch"] <= bundle["restriction_evidence"]["epoch"]
            or not _instant(batch["source_sealed_at"]) <= _instant(batch["imported_at"]) <= _instant(anchor["created_at"]) <= _instant(bundle["created_at"])):
        raise ValueError()
    validate_evolution(bundle["core"], bundle["conversations"], recovery, anchor)
    # Source audit remains source evidence, not new trusted local audit. It is
    # complete/closed even after local writes and no longer constrained to the
    # target restorer as original source author.
    audit = recovery["conversation_source_audit"]
    if any(row["attempt_id"] != batch["attempt_id"] or row["source_workspace_id"] != batch["source_workspace_id"] for row in audit):
        raise ValueError()
    from .exit_package import AUDIT_COLUMNS
    normalized = [{**{key: row[key] for key in AUDIT_COLUMNS}, "workspace_id": row["source_workspace_id"]} for row in audit]
    validate_audit(normalized, batch["source_workspace_id"], batch["source_owner_id"], _instant(batch["source_sealed_at"]))
    return counts
