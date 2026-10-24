"""Explicit v3 pre-transfer evidence; old v2 validators are not widened."""
from copy import deepcopy
from types import MappingProxyType

import rfc8785

from .conversation_exit import CONVERSATION_COLUMNS as V2_COLUMNS, MAX_BYTES, snapshot_hash, validate_v2
from .exit_package import checksum


SCHEMA = "classmatter.synthetic-exit.v3"
TRANSFER_COLUMNS = ("transfer_id", "transfer_hash", "transfer_at")
CONVERSATION_COLUMNS = MappingProxyType({**V2_COLUMNS,
    "conversation_control": (*V2_COLUMNS["conversation_control"], *TRANSFER_COLUMNS)})


def build_package(workspace, actor, now, core, conversations, proof, audit):
    from .conversation_exit import build_package as build_v2
    projected = deepcopy(conversations)
    for row in projected["conversation_control"]:
        for key in TRANSFER_COLUMNS:
            row.pop(key)
    bundle = build_v2(workspace, actor, now, core, projected, proof, audit)
    bundle.update(schema_version=SCHEMA, source_revision="0020", conversations=conversations,
                  snapshot_hash=snapshot_hash(core, conversations, proof))
    bundle["package_checksum"] = checksum({key: value for key, value in bundle.items() if key != "package_checksum"})
    validate_v3(bundle)
    return bundle


def validate_v3(bundle, *, require_complete=False):
    try:
        if (type(bundle) is not dict or bundle["schema_version"] != SCHEMA or bundle["source_revision"] != "0020"
                or bundle["snapshot_hash"] != snapshot_hash(bundle["core"], bundle["conversations"], bundle["restriction_evidence"])
                or bundle["package_checksum"] != checksum({key: value for key, value in bundle.items() if key != "package_checksum"})
                or len(rfc8785.dumps(bundle)) > MAX_BYTES):
            raise ValueError()
        projected = deepcopy(bundle)
        for row in projected["conversations"]["conversation_control"]:
            if set(row) != set(CONVERSATION_COLUMNS["conversation_control"]) or any(row[key] is not None for key in TRANSFER_COLUMNS):
                raise ValueError()  # Frozen source never emits another ordinary exit.
            for key in TRANSFER_COLUMNS:
                row.pop(key)
        projected.update(schema_version="classmatter.synthetic-exit.v2", source_revision="0019")
        projected["snapshot_hash"] = snapshot_hash(projected["core"], projected["conversations"], projected["restriction_evidence"])
        projected["package_checksum"] = checksum({key: value for key, value in projected.items() if key != "package_checksum"})
        return validate_v2(projected, require_complete=require_complete)
    except Exception:
        raise ValueError("Invalid or frozen synthetic v3 exit; no target admission") from None
