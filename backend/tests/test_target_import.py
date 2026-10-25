"""Synthetic closed formats and target file evidence, not recovery admission."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import os
import multiprocessing
import subprocess
import sys
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from class_os.domain.conversation_exit_v3 import build_package as build_v3, validate_v3
from class_os.domain.conversation_exit_v4 import build_package, validate_v4
from class_os.domain.exit_package import checksum
from class_os.domain.source_transfer import SourceFence, SealConversationSource, CommittedSource
from class_os.domain.target_import import (RecoveryCandidate, StageConversationImport, TargetFence, decode_import, decode_target, IMPORT_COLUMNS, ENTITY_KEYS, provenance_rows)
from class_os.domain.roster import decode
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions
from class_os.infrastructure.target_import import ProtectedTargetImport, ImportUnavailable, FILE_NAME
from test_conversation_exit import sample
from test_model_secrets import fixture_codec


def native():
    old = sample()
    for row in old["conversations"]["conversation_control"]:
        row.update(transfer_id=None, transfer_hash=None, transfer_at=None)
    for row in old["conversations"]["conversation_run"]:
        row.update(state="cancelled", version=2, ended_at=old["created_at"])
    return build_package(UUID(old["workspace_id"]), UUID(old["actor_refs"][0]), datetime.fromisoformat(old["created_at"]),
                         old["core"], old["conversations"], old["restriction_evidence"], old["audit_refs"], {k: [] for k in IMPORT_COLUMNS})


def candidate():
    bundle = native()
    target, owner = uuid4(), uuid4()
    at, proof = datetime.fromisoformat(bundle["created_at"]), bundle["restriction_evidence"]
    seal = SealConversationSource(uuid4(), uuid4(), bundle["package_checksum"], target, owner, "b" * 64)
    fence = SourceFence(UUID(bundle["workspace_id"]), UUID(bundle["actor_refs"][0]), UUID(proof["authority_id"]),
                        proof["epoch"], proof["source_head_hash"], seal, at)
    source = CommittedSource(fence, "c" * 64, uuid4(), "d" * 64)
    command = StageConversationImport(seal.attempt_id, bundle["package_checksum"], source.fence_hash)
    return RecoveryCandidate.from_bundle(bundle), command, source, target, owner, at


def test_closed_candidate_and_command_do_not_grant_r1_or_offline_authority():
    value, command, source, target, owner, at = candidate()
    assert value.match(command, source, target, owner, "b" * 64, at) == value.bundle()
    assert decode_import(command.canonical()) == command
    with pytest.raises(ValueError):
        decode(command.canonical())
    with pytest.raises(ValueError):
        decode_import({**command.canonical(), "activation_allowed": True})
    for wrong in (None, source.canonical(), object()):
        with pytest.raises(ValueError):
            value.match(command, wrong, target, owner, "b" * 64, at)
    for values in ((uuid4(), owner, "b" * 64), (target, uuid4(), "b" * 64), (target, owner, "e" * 64)):
        with pytest.raises(ValueError):
            value.match(command, source, *values, at)
    altered = value.bundle()
    altered["core"]["student"][0]["name"] = "合成调用者改名"
    assert value.bundle() != altered


@pytest.mark.parametrize("fault", ["active", "unknown", "checksum", "oversize", "noncanonical"])
def test_bad_candidate_refused_without_io(fault):
    value = native()
    if fault == "active":
        value["conversations"]["conversation_run"][0].update(state="queued", version=1, ended_at=None)
        from class_os.domain.conversation_exit_v4 import snapshot_hash
        value["snapshot_hash"] = snapshot_hash(value["core"], value["conversations"], value["restriction_evidence"], value["recovery"])
        value["package_checksum"] = checksum({k: v for k, v in value.items() if k != "package_checksum"})
    elif fault == "unknown":
        value["sql"] = "not a command"
    elif fault == "checksum":
        value["package_checksum"] = "0" * 64
    with pytest.raises(ValueError):
        if fault == "oversize":
            RecoveryCandidate(b" " * 1048577)
        elif fault == "noncanonical":
            RecoveryCandidate(b" " + RecoveryCandidate.from_bundle(value).encoded)
        else:
            RecoveryCandidate.from_bundle(value)


def test_v4_does_not_widen_v3_and_genuine_v3_still_valid():
    value = native()
    assert len(validate_v4(value)) == 16
    with pytest.raises(ValueError):
        validate_v3(value)
    with pytest.raises(ValueError):
        validate_v4(value, require_complete=True)
    old = build_v3(UUID(value["workspace_id"]), UUID(value["actor_refs"][0]), datetime.fromisoformat(value["created_at"]),
                   value["core"], value["conversations"], value["restriction_evidence"], value["audit_refs"])
    assert len(validate_v3(old)) == 13
    assert RecoveryCandidate.from_bundle(old).bundle() == old
    for key in ("conversation_import", "conversation_provenance", "conversation_source_audit"):
        bad = deepcopy(value)
        bad["recovery"][key] = [{}]
        bad["snapshot_hash"] = "0" * 64
        bad["package_checksum"] = checksum({k: v for k, v in bad.items() if k != "package_checksum"})
        with pytest.raises(ValueError):
            validate_v4(bad)


def pending():
    value, command, source, target, owner, at = candidate()
    bundle = value.bundle()
    core, conversations = deepcopy(bundle["core"]), deepcopy(bundle["conversations"])
    for row in core["workspace"]:
        row["workspace_id"] = str(target)
    for kind in ENTITY_KEYS:
        for row in (core if kind in core else conversations)[kind]:
            row["workspace_id"] = str(target)
            for field in ("created_by", "updated_by", "recorded_by", "owner_id"):
                if field in row:
                    row[field] = str(owner)
    authority = str(uuid4())
    conversations["conversation_control"][0].update(workspace_id=str(target), owner_id=str(owner), authority_id=authority, head_hash="e" * 64)
    proof = {**bundle["restriction_evidence"], "authority_id": authority, "source_head_hash": "e" * 64}
    batch = {"workspace_id": str(target), "attempt_id": str(command.attempt_id), "restorer_id": str(owner),
        "source_workspace_id": str(source.fence.workspace_id), "source_owner_id": str(source.fence.owner_id),
        "source_authority_id": str(source.fence.authority_id), "source_epoch": source.fence.restriction_epoch,
        "source_head_hash": source.fence.restriction_hash, "source_fence_hash": source.fence_hash,
        "source_receipt_id": str(source.receipt_id), "source_root_binding": source.root_binding,
        "package_hash": command.package_hash, "target_binding": "b" * 64,
        "source_sealed_at": at.isoformat(), "imported_at": at.isoformat(), "phase": "pending"}
    recovery = {"conversation_import": [batch], "conversation_provenance": provenance_rows(bundle, target, command.attempt_id),
        "conversation_source_audit": [{"workspace_id": str(target), "attempt_id": str(command.attempt_id),
            "source_workspace_id": str(source.fence.workspace_id), "event_id": str(uuid4()), "actor_id": str(source.fence.owner_id),
            "purpose": "manage-roster", "action": "command.commit", "outcome": "allowed", "occurred_at": at.isoformat(),
            "proposal_id": None, "payload_hash": None, "receipt_id": None, "resource_id": None, "resource_version": None,
            "class_id": None, "term_id": None}]}
    return build_package(target, owner, at, core, conversations, proof, [], recovery)


@pytest.mark.parametrize("fault", ["null-event", "bool-event", "bad-event", "bool-version", "false-version", "missing-origin", "duplicate-origin", "origin-hash", "wrong-actor", "admitted", "unknown-column"])
def test_rehashed_v4_provenance_and_audit_are_strict(fault):
    value = pending()
    assert validate_v4(value)
    recovery = value["recovery"]
    if fault in ("null-event", "bool-event", "bad-event"):
        recovery["conversation_source_audit"][0]["event_id"] = {"null-event": None, "bool-event": True, "bad-event": "not-a-uuid"}[fault]
    elif fault == "bool-version":
        row = next(r for r in recovery["conversation_provenance"] if r["source_version"] == 1)
        row["source_version"] = True
    elif fault == "false-version":
        row = next(r for r in recovery["conversation_provenance"] if r["source_version"] == 0)
        row["source_version"] = False
    elif fault == "missing-origin":
        recovery["conversation_provenance"].pop()
    elif fault == "duplicate-origin":
        recovery["conversation_provenance"].append(deepcopy(recovery["conversation_provenance"][0]))
    elif fault == "origin-hash":
        recovery["conversation_provenance"][0]["source_hash"] = "0" * 64
    elif fault == "wrong-actor":
        recovery["conversation_import"][0]["source_owner_id"] = value["actor_refs"][0]
    elif fault == "admitted":
        recovery["conversation_import"][0]["phase"] = "admitted"
    else:
        recovery["conversation_provenance"][0]["extra"] = {}
    from class_os.domain.conversation_exit_v4 import snapshot_hash
    value["snapshot_hash"] = snapshot_hash(value["core"], value["conversations"], value["restriction_evidence"], recovery)
    value["package_checksum"] = checksum({k: v for k, v in value.items() if k != "package_checksum"})
    with pytest.raises(ValueError):
        validate_v4(value)


def test_single_hop_input_explicitly_refuses_valid_imported_package():
    value = pending()
    assert validate_v4(value)
    with pytest.raises(ValueError, match="Multi-hop"):
        RecoveryCandidate.from_bundle(value)


def test_new_v4_proof_audit_is_not_dropped_or_admitted_to_v3():
    value = native()
    audit = {"workspace_id": value["workspace_id"], "event_id": str(uuid4()), "actor_id": value["actor_refs"][0],
        "purpose": "exit-recovery", "action": "conversation.transfer.proof", "outcome": "denied", "occurred_at": value["created_at"],
        "proposal_id": None, "payload_hash": None, "receipt_id": None, "resource_id": str(uuid4()), "resource_version": None,
        "class_id": None, "term_id": None}
    args = (UUID(value["workspace_id"]), UUID(value["actor_refs"][0]), datetime.fromisoformat(value["created_at"]),
            value["core"], value["conversations"], value["restriction_evidence"])
    current = build_package(*args, [audit], value["recovery"])
    assert current["audit_refs"] == [audit] and validate_v4(current)
    with pytest.raises(ValueError):
        build_v3(*args, [audit])
    with pytest.raises(ValueError):
        build_package(*args, [{**audit, "action": "unknown.proof"}], value["recovery"])
    restored = pending()
    batch = restored["recovery"]["conversation_import"][0]
    restored["recovery"]["conversation_source_audit"][0].update(action="conversation.transfer.proof", purpose="exit-recovery")
    from class_os.domain.conversation_exit_v4 import snapshot_hash
    restored["snapshot_hash"] = snapshot_hash(restored["core"], restored["conversations"], restored["restriction_evidence"], restored["recovery"])
    restored["package_checksum"] = checksum({k: v for k, v in restored.items() if k != "package_checksum"})
    assert validate_v4(restored)


def test_genuine_v3_and_v4_offline_profiles_remain_separate(tmp_path):
    value = native()
    old = build_v3(UUID(value["workspace_id"]), UUID(value["actor_refs"][0]), datetime.fromisoformat(value["created_at"]),
                   value["core"], value["conversations"], value["restriction_evidence"], value["audit_refs"])
    import rfc8785
    verifier = Path(__file__).resolve().parents[1] / "verify_exit.py"
    for bundle, profile, wrong in ((old, "conversation-v3", "conversation-v4"), (value, "conversation-v4", "conversation-v3")):
        path = tmp_path / (profile + ".json")
        path.write_bytes(rfc8785.dumps(bundle))
        result = subprocess.run([sys.executable, str(verifier), str(path), "--profile", profile], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and json.loads(result.stdout)["activation_allowed"] is False
        result = subprocess.run([sys.executable, str(verifier), str(path), "--profile", wrong], capture_output=True, text=True, timeout=10)
        assert result.returncode == 1


def target_port(tmp_path, codec=fixture_codec):
    value, command, source, target, owner, at = candidate()
    restrictions = ProtectedConversationRestrictions(tmp_path, target, codec=codec)
    fence = TargetFence(target, owner, uuid4(), "a" * 64, command, source.receipt_id, at)
    return ProtectedTargetImport(restrictions), fence


def test_target_file_is_exclusive_reopenable_and_closed(tmp_path):
    port, fence = target_port(tmp_path)
    assert not port.present()
    digest = port.stage(fence)
    original = (tmp_path / FILE_NAME).read_bytes()
    assert len(digest) == 64 and port.stage(fence) == digest
    assert ProtectedTargetImport(port.restrictions).read() == fence
    assert decode_target(fence.canonical()) == fence
    with pytest.raises(ValueError):
        decode_target({**fence.canonical(), "admit": True})
    with pytest.raises(ImportUnavailable):
        port.stage(replace(fence, owner_id=uuid4()))
    assert (tmp_path / FILE_NAME).read_bytes() == original


@pytest.mark.parametrize("fault", ["missing", "corrupt", "directory", "hardlink", "oversize", "wrong-root", "wrong-workspace"])
def test_invalid_target_evidence_never_admits(tmp_path, fault):
    port, fence = target_port(tmp_path)
    port.stage(fence)
    path = tmp_path / FILE_NAME
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"synthetic-invalid-evidence")
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    elif fault == "hardlink":
        os.link(path, tmp_path / "synthetic-second-link")
    elif fault == "oversize":
        path.write_bytes(b"x" * 32769)
    elif fault == "wrong-root":
        other = tmp_path / "other"
        other.mkdir()
        (other / FILE_NAME).write_bytes(path.read_bytes())
        port = ProtectedTargetImport(ProtectedConversationRestrictions(other, fence.workspace_id, codec=fixture_codec))
    else:
        port = ProtectedTargetImport(ProtectedConversationRestrictions(tmp_path, uuid4(), codec=fixture_codec))
    with pytest.raises(ImportUnavailable):
        port.read()


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI only")
def test_actual_dpapi_target_metadata(tmp_path):
    from class_os.infrastructure.local_runtime import protect
    port, fence = target_port(tmp_path, protect)
    port.stage(fence)
    assert fence.command.package_hash.encode() not in (tmp_path / FILE_NAME).read_bytes()
    assert port.read() == fence


@pytest.mark.parametrize("fault", ["fsync", "link"])
def test_target_publish_failure_has_no_partial_visible_file(tmp_path, monkeypatch, fault):
    port, fence = target_port(tmp_path)
    monkeypatch.setattr(os, fault, lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic publication fault")))
    with pytest.raises(ImportUnavailable):
        port.stage(fence)
    assert not port.present()
    assert not list(tmp_path.glob(".target-import-*.pending"))


def _target_crash(root, fence, during_link):
    port = ProtectedTargetImport(ProtectedConversationRestrictions(root, fence.workspace_id, codec=fixture_codec))
    if during_link:
        original = os.link
        def crash(*args, **kwargs):
            original(*args, **kwargs)
            os._exit(0)
        os.link = crash
    port.stage(fence)
    os._exit(0)


@pytest.mark.parametrize("during_link", [False, True])
def test_actual_target_process_crash_preserves_pending_and_releases_lock(tmp_path, during_link):
    port, fence = target_port(tmp_path)
    process = multiprocessing.get_context("spawn").Process(target=_target_crash, args=(tmp_path, fence, during_link))
    try:
        process.start()
        process.join(timeout=15)
        assert process.exitcode == 0 and port.present()
        with port.restrictions._locked():
            pass
        if during_link:
            with pytest.raises(ImportUnavailable):
                port.read()
        else:
            assert port.read() == fence
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        process.close()
