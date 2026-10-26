"""V6-only fixed result provenance; legacy registries/validators stay frozen."""
from copy import deepcopy
from types import MappingProxyType

from .target_import import ENTITY_KEYS as LEGACY_KEYS, IMPORT_COLUMNS, provenance_rows as legacy_provenance
from .recovery_admission import (make_origins as legacy_origins, origins_hash, origin_key,
    validate_evolution as legacy_evolution, validate_origins as legacy_validate_origins, ADMISSION_COLUMNS)
from .conversation_results import RESULT_COLUMNS, RESULT_ENTITY_KEYS
from .conversation_exit import _uuid, _hash, _instant, MAX_ROWS
from .exit_package import checksum


ENTITY_KEYS = MappingProxyType({**LEGACY_KEYS, **RESULT_ENTITY_KEYS})


def original_result(row, batch):
    return {**row, "workspace_id": batch["source_workspace_id"]}


def legacy_recovery(recovery):
    """Private validation projection, never an emitted proof or authority."""
    projected = deepcopy(recovery)
    for key in ("conversation_provenance", "conversation_origin"):
        projected[key] = [row for row in projected[key] if row["entity_kind"] not in RESULT_COLUMNS]
    if projected["conversation_admission"]:
        anchor, = projected["conversation_admission"]
        anchor.update(origin_count=len(projected["conversation_origin"]), origins_hash=origins_hash(projected["conversation_origin"]))
    return projected


def provenance_rows(bundle, workspace, attempt):
    rows = legacy_provenance(bundle, workspace, attempt)
    for kind, key in RESULT_ENTITY_KEYS.items():
        for row in bundle["conversations"].get(kind, []):
            rows.append({"workspace_id": str(workspace), "attempt_id": str(attempt), "entity_kind": kind,
                "thread_id": row["thread_id"], "resource_id": row[key], "source_version": 0, "source_hash": checksum(row)})
    return rows


def make_origins(core, conversations, recovery):
    rows = legacy_origins(core, conversations, legacy_recovery(recovery))
    batch, = recovery["conversation_import"]
    for item in recovery["conversation_provenance"]:
        kind = item["entity_kind"]
        if kind not in RESULT_COLUMNS:
            continue
        row, = [row for row in conversations[kind] if row["thread_id"] == item["thread_id"]
                and row[RESULT_ENTITY_KEYS[kind]] == item["resource_id"]]
        original = original_result(row, batch)
        if item["source_version"] != 0 or checksum(original) != item["source_hash"]:
            raise ValueError("Only exact pending result origins may be admitted")
        identity = {key: value for key, value in original.items() if kind != "conversation_task_draft" or key not in ("title", "visibility")}
        rows.append({**item, "identity_hash": checksum(identity), "body_hash": checksum(original["title"]) if kind == "conversation_task_draft" else None,
                     "source_open": False, "initial_state": None})
    return sorted(rows, key=origin_key)


def validate_result_provenance(core, conversations, recovery):
    imports, anchors, origins = (recovery[key] for key in ("conversation_import", "conversation_admission", "conversation_origin"))
    provenance = recovery["conversation_provenance"]
    if any(type(row) is not dict or set(row) != set(IMPORT_COLUMNS["conversation_provenance"]) for row in provenance):
        raise ValueError("Unknown v6 provenance columns")
    if not imports:
        if anchors or origins or provenance:
            raise ValueError("Orphan result recovery evidence")
        return
    batch, = imports
    extra = [row for row in provenance if row["entity_kind"] in RESULT_COLUMNS]
    indexes = {kind: {(row["thread_id"], row[RESULT_ENTITY_KEYS[kind]]): row for row in conversations[kind]} for kind in RESULT_COLUMNS}
    if any(item["entity_kind"] not in ENTITY_KEYS for item in provenance):
        raise ValueError("Unknown v6 provenance kind")
    if not anchors:
        if origins:
            raise ValueError("Unadmitted result origins")
        expected = {(kind, row["thread_id"], row[RESULT_ENTITY_KEYS[kind]]) for kind in RESULT_COLUMNS for row in conversations[kind]}
        actual = {(row["entity_kind"], row["thread_id"], row["resource_id"]) for row in extra}
        if actual != expected or len(actual) != len(extra):
            raise ValueError("Pending result provenance incomplete")
        for item in extra:
            row = indexes[item["entity_kind"]][item["thread_id"], item["resource_id"]]
            validate_metadata(item, batch)
            if checksum(original_result(row, batch)) != item["source_hash"]:
                raise ValueError("Pending result fingerprint changed")
        return
    anchor, = anchors
    if type(origins) is not list or len(origins) > MAX_ROWS or type(anchor["origin_count"]) is not int or anchor["origin_count"] != len(origins) or origins_hash(origins) != anchor["origins_hash"]:
        raise ValueError("Full v6 origin registry changed")
    projected = legacy_recovery(recovery)
    old_anchor, = projected["conversation_admission"]
    legacy_validate_origins(projected["conversation_origin"], projected["conversation_provenance"], old_anchor)
    legacy_evolution(core, conversations, projected, old_anchor)
    added = [row for row in origins if row["entity_kind"] in RESULT_COLUMNS]
    if any(row["entity_kind"] not in ENTITY_KEYS for row in origins) or len(added) != len(extra):
        raise ValueError("Incomplete result origins")
    expected = {origin_key(row): row for row in extra}
    seen = set()
    for origin in added:
        if type(origin) is not dict or set(origin) != set(ADMISSION_COLUMNS["conversation_origin"]):
            raise ValueError("Unknown result origin fields")
        validate_metadata(origin, batch)
        key = origin_key(origin)
        projected_item = {key: origin[key] for key in IMPORT_COLUMNS["conversation_provenance"]}
        if key in seen or projected_item != expected.get(key):
            raise ValueError("Result origin added or relabeled")
        seen.add(key)
        _hash(origin["identity_hash"])
        kind = origin["entity_kind"]
        row = indexes[kind].get((origin["thread_id"], origin["resource_id"]))
        if row is None or origin["source_open"] is not False or origin["initial_state"] is not None:
            raise ValueError("Result origin removed or reopened")
        original = original_result(row, batch)
        identity = {key: value for key, value in original.items() if kind != "conversation_task_draft" or key not in ("title", "visibility")}
        if checksum(identity) != origin["identity_hash"]:
            raise ValueError("Immutable result identity changed")
        if kind == "conversation_task_draft":
            _hash(origin["body_hash"])
            if row["visibility"] == "visible" and checksum(row["title"]) != origin["body_hash"]:
                raise ValueError("Imported draft content changed")
        elif origin["body_hash"] is not None:
            raise ValueError("Source receipt has no body")
        if not (kind == "conversation_task_draft" and row["visibility"] == "restricted") and checksum(original) != origin["source_hash"]:
            raise ValueError("Immutable result content changed")
    imported_keys = {(row["entity_kind"], row["thread_id"], row["resource_id"]) for row in added}
    for kind, rows in indexes.items():
        for (thread, resource), row in rows.items():
            recorded = row["recorded_at"] if kind == "conversation_result_receipt" and row["protocol"] == "legacy-plain" else row["created_at"]
            if (kind, thread, resource) not in imported_keys and _instant(recorded) < _instant(anchor["created_at"]):
                raise ValueError("Unattributed result predates admission")


def validate_metadata(row, batch):
    for key in ("workspace_id", "attempt_id", "resource_id", "thread_id"):
        _uuid(row[key])
    _hash(row["source_hash"])
    if (row["workspace_id"] != batch["workspace_id"] or row["attempt_id"] != batch["attempt_id"]
            or type(row["source_version"]) is not int or row["source_version"] != 0):
        raise ValueError("Invalid result provenance scope")


def admission_capacity_projection(core, conversations, recovery):
    from .recovery_admission import admission_capacity_projection as legacy_capacity
    projected = legacy_capacity(core, conversations, legacy_recovery(recovery))
    anchor, = projected["conversation_admission"]
    rows = make_origins(core, conversations, recovery)
    return {**recovery, "conversation_admission": [{**anchor, "origin_count": len(rows), "origins_hash": origins_hash(rows)}],
            "conversation_origin": rows}
