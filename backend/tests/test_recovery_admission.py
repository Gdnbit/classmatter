"""Closed v5 evolution proofs only; no SQL, file publication or admission."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json
from uuid import UUID, uuid4

import pytest

from class_os.domain.conversation_exit_v4 import validate_v4, snapshot_hash
from class_os.domain.conversation_exit_v5 import build_package, validate_v5
from class_os.domain.exit_package import checksum
from class_os.domain.recovery_admission import (RECOVERY_COLUMNS, make_origins, origins_hash,
    AdmitConversationTarget, AdmissionFence, decode_admission, decode_admission_fence, source_audit_hash)
from class_os.domain.source_retirement import CommittedRetirement
from class_os.domain.roster import decode
from test_target_import import pending, native
from test_source_retirement import evidence


def sample(*, admitted=True, imported=True):
    old = pending() if imported else native()
    core, conversations, proof = deepcopy(old["core"]), deepcopy(old["conversations"]), deepcopy(old["restriction_evidence"])
    recovery = {key: deepcopy(old["recovery"].get(key, [])) for key in RECOVERY_COLUMNS}
    at = datetime.fromisoformat(old["created_at"])
    if admitted:
        assert imported
        batch = recovery["conversation_import"][0]
        rows = make_origins(core, conversations, recovery)
        at += timedelta(seconds=1)
        recovery["conversation_origin"] = rows
        recovery["conversation_admission"] = [{"workspace_id": old["workspace_id"], "attempt_id": batch["attempt_id"],
            "owner_id": old["actor_refs"][0], "authority_id": proof["authority_id"], "target_binding": batch["target_binding"],
            "retirement_hash": "a" * 64, "retirement_receipt_id": str(uuid4()), "stage_hash": old["snapshot_hash"],
            "stage_receipt_id": str(uuid4()), "target_fence_hash": "b" * 64, "origins_hash": origins_hash(rows),
            "origin_count": len(rows), "created_at": at.isoformat(), "receipt_id": str(uuid4()), "proof_hash": "c" * 64}]
        recovery["conversation_admission"][0].update(batch_hash=checksum(batch),
            source_audit_hash=source_audit_hash(recovery["conversation_source_audit"]))
    return build_package(UUID(old["workspace_id"]), UUID(old["actor_refs"][0]), at, core, conversations, proof, [], recovery)


def rehash(value, *, registry=False):
    if registry:
        value["recovery"]["conversation_admission"][0]["origins_hash"] = origins_hash(value["recovery"]["conversation_origin"])
    value["snapshot_hash"] = snapshot_hash(value["core"], value["conversations"], value["restriction_evidence"], value["recovery"])
    value["package_checksum"] = checksum({key: row for key, row in value.items() if key != "package_checksum"})


def advance(value):
    at = datetime.fromisoformat(value["created_at"]) + timedelta(seconds=1)
    value["created_at"] = at.isoformat()
    return at.isoformat()


def test_native_pending_and_admitted_are_separate_from_unchanged_v4():
    for value in (sample(admitted=False, imported=False), sample(admitted=False), sample()):
        assert len(validate_v5(value)) == 18 and value["activation_allowed"] is False
        with pytest.raises(ValueError):
            validate_v4(value)
        with pytest.raises(ValueError):
            validate_v5(value, require_complete=True)
    assert validate_v4(pending())  # Historical exact pending evidence retained.


def test_native_versioned_edit_and_new_record_revision_preserve_originals():
    value = sample()
    at = advance(value)
    student = value["core"]["student"][0]
    student.update(name="合成本地更名", version=student["version"] + 1, updated_at=at)
    record = deepcopy(value["core"]["record_revision"][-1])
    record.update(version=record["version"] + 1, recorded_at=at, fact_text="合成本地更正",
                  revision_kind="correct", revision_reason="合成本地手动更正")
    value["core"]["record_revision"].append(record)
    rehash(value)
    assert validate_v5(value)
    assert len(value["recovery"]["conversation_provenance"]) == len(value["recovery"]["conversation_origin"])


def test_clear_uses_marker_null_and_hashes_without_baseline_body_copies():
    value = sample()
    original = value["conversations"]["conversation_message"][0]["body"]
    at = advance(value)
    thread = value["conversations"]["conversation_thread"][0]
    thread.update(status="cleared", title="已清除的会话", version=thread["version"] + 1, updated_at=at, cleared_at=at)
    for row in value["conversations"]["conversation_message"]:
        row.update(body=None, visibility="restricted")
    proof = value["restriction_evidence"]
    proof.update(epoch=1, source_head_hash="f" * 64,
                 markers=[{"thread_id": thread["thread_id"], "version_after": thread["version"], "restricted_at": at}])
    value["conversations"]["conversation_control"][0].update(epoch=1, head_hash=proof["source_head_hash"], updated_at=at)
    rehash(value)
    assert validate_v5(value)
    assert original not in json.dumps(value["recovery"], ensure_ascii=False)
    changed = deepcopy(value)
    changed["conversations"]["conversation_message"][0]["body"] = original
    rehash(changed)
    with pytest.raises(ValueError):
        validate_v5(changed)


@pytest.mark.parametrize("fault", ["same-version-name", "creation-time", "body", "run-restart", "old-revision", "missing-entity",
    "origin-extra", "origin-missing", "origin-identity", "provenance-hash", "bool-version", "false-open", "body-digest", "wrong-state",
    "bool-count", "wrong-owner", "wrong-authority", "wrong-root", "phase", "source-epoch", "activation", "extra-collection",
    "batch-package", "batch-receipt", "source-audit-missing"])
def test_rehashed_invalid_evolution_never_passes(fault):
    value = sample()
    at = advance(value)
    registry = False
    if fault == "same-version-name":
        value["core"]["student"][0]["name"] = "合成未增版本篡改"
    elif fault == "creation-time":
        row = value["core"]["student"][0]
        row.update(created_at=at, updated_at=at, version=row["version"] + 1)
    elif fault == "body":
        value["conversations"]["conversation_message"][0]["body"] = "合成替换正文"
    elif fault == "run-restart":
        row = value["conversations"]["conversation_run"][0]
        row.update(state="queued", version=1, ended_at=None)
    elif fault == "old-revision":
        value["core"]["record_revision"][0]["fact_text"] = "合成原版本篡改"
    elif fault == "missing-entity":
        value["conversations"]["conversation_turn"] = []
    elif fault == "origin-extra":
        value["recovery"]["conversation_origin"].append(deepcopy(value["recovery"]["conversation_origin"][0]))
    elif fault == "origin-missing":
        value["recovery"]["conversation_origin"].pop()
    elif fault == "origin-identity":
        value["recovery"]["conversation_origin"][0]["identity_hash"] = "0" * 64
    elif fault == "provenance-hash":
        value["recovery"]["conversation_provenance"][0]["source_hash"] = "0" * 64
    elif fault == "bool-version":
        value["recovery"]["conversation_origin"][0]["source_version"] = True
        registry = True
    elif fault == "false-open":
        value["recovery"]["conversation_origin"][0]["source_open"] = 0
        registry = True
    elif fault == "body-digest":
        row = next(row for row in value["recovery"]["conversation_origin"] if row["entity_kind"] == "conversation_message")
        row["body_hash"] = "0" * 64
        registry = True
    elif fault == "wrong-state":
        value["recovery"]["conversation_origin"][0]["initial_state"] = "arbitrary"
        registry = True
    elif fault in ("bool-count", "wrong-owner", "wrong-authority", "wrong-root"):
        anchor = value["recovery"]["conversation_admission"][0]
        anchor.update({"bool-count": {"origin_count": True}, "wrong-owner": {"owner_id": str(uuid4())},
                       "wrong-authority": {"authority_id": str(uuid4())}, "wrong-root": {"target_binding": "0" * 64}}[fault])
    elif fault == "phase":
        value["recovery"]["conversation_import"][0]["phase"] = "admitted"
    elif fault == "source-epoch":
        value["recovery"]["conversation_import"][0]["source_epoch"] = True
    elif fault == "activation":
        value["activation_allowed"] = True
    elif fault == "batch-package":
        value["recovery"]["conversation_import"][0]["package_hash"] = "0" * 64
    elif fault == "batch-receipt":
        value["recovery"]["conversation_import"][0]["source_receipt_id"] = str(uuid4())
    elif fault == "source-audit-missing":
        assert value["recovery"]["conversation_source_audit"]
        value["recovery"]["conversation_source_audit"].pop()
    else:
        value["recovery"]["custom_fact"] = []
    rehash(value, registry=registry)
    with pytest.raises(ValueError):
        validate_v5(value)


def test_typed_admission_witness_is_closed_and_not_a_r1_command(tmp_path):
    _, retirement = evidence(tmp_path)
    proof = CommittedRetirement(retirement, "a" * 64, uuid4())
    command = AdmitConversationTarget(retirement.command.attempt_id, proof.proof_hash, retirement.stage.snapshot_hash, "b" * 64)
    fence = AdmissionFence(proof, command, 8, "d" * 64, "e" * 64, uuid4(), retirement.created_at + timedelta(seconds=1))
    assert decode_admission(command.canonical()) == command
    assert decode_admission_fence(fence.canonical()) == fence
    assert fence.anchor("c" * 64)["owner_id"] == str(retirement.stage.fence.owner_id)
    for invalid in ({**command.canonical(), "activate": True}, {**command.canonical(), "attempt_id": str(uuid4()).upper()}):
        with pytest.raises(ValueError):
            decode_admission(invalid)
    with pytest.raises(ValueError):
        decode(command.canonical())
    for fields in ({"origin_count": True}, {"retirement": proof.fence.canonical()},
                   {"command": replace(command, expected_stage_hash="0" * 64)}):
        with pytest.raises(ValueError):
            replace(fence, **fields)
