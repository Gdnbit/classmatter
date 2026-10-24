"""Synthetic source-only fence evidence; never target admission."""
from dataclasses import replace
from datetime import datetime, timezone
import os
import multiprocessing
from uuid import uuid4
from uuid import UUID
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import json

import rfc8785

import pytest

from class_os.domain.source_transfer import SealConversationSource, SourceFence, decode_fence, decode_seal
from class_os.domain.roster import decode
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions
from class_os.infrastructure.source_transfer import ProtectedSourceTransfer, TransferUnavailable, FILE_NAME
from test_model_secrets import fixture_codec


def fence():
    return SourceFence(uuid4(), uuid4(), uuid4(), 0, "a" * 64,
        SealConversationSource(uuid4(), uuid4(), "b" * 64, uuid4(), uuid4(), "c" * 64), datetime.now(timezone.utc))


def test_closed_values_are_not_r1_commands_or_target_grants():
    value = fence()
    assert decode_fence(value.canonical()) == value and decode_seal(value.command.canonical()) == value.command
    with pytest.raises(ValueError):
        decode(value.command.canonical())
    for changed in ({**value.command.canonical(), "activate": True}, {**value.canonical(), "state": "admitted"}):
        with pytest.raises(ValueError):
            (decode_seal if "command" in changed and type(changed["command"]) is str else decode_fence)(changed)
    for values in ({"restriction_epoch": True}, {"restriction_hash": ""}, {"owner_id": value.command.target_owner_id},
                   {"workspace_id": value.command.target_workspace_id}, {"created_at": datetime.now()}):
        with pytest.raises(ValueError):
            replace(value, **values)


def test_exclusive_file_reopens_and_same_seal_is_idempotent(tmp_path):
    value = fence()
    restrictions = ProtectedConversationRestrictions(tmp_path, value.workspace_id, codec=fixture_codec)
    port = ProtectedSourceTransfer(restrictions)
    assert port.present() is False
    digest = port.seal(value)
    path = tmp_path / FILE_NAME
    sealed = path.read_bytes()
    assert port.present() is True and len(digest) == 64
    assert ProtectedSourceTransfer(restrictions).read() == value
    assert port.seal(value) == digest and path.read_bytes() == sealed
    with pytest.raises(TransferUnavailable):
        port.seal(replace(value, command=replace(value.command, attempt_id=uuid4())))
    assert path.read_bytes() == sealed


@pytest.mark.parametrize("fault", ["missing", "corrupt", "directory", "hardlink", "copy-root", "wrong-workspace", "large"])
def test_uncertain_evidence_never_becomes_absence_or_authority(tmp_path, fault):
    value = fence()
    port = ProtectedSourceTransfer(ProtectedConversationRestrictions(tmp_path, value.workspace_id, codec=fixture_codec))
    port.seal(value)
    path = tmp_path / FILE_NAME
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"synthetic-corrupt")
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    elif fault == "hardlink":
        os.link(path, tmp_path / "extra")
    elif fault == "copy-root":
        other = tmp_path / "other"
        other.mkdir()
        (other / FILE_NAME).write_bytes(path.read_bytes())
        port = ProtectedSourceTransfer(ProtectedConversationRestrictions(other, value.workspace_id, codec=fixture_codec))
    elif fault == "wrong-workspace":
        port = ProtectedSourceTransfer(ProtectedConversationRestrictions(tmp_path, uuid4(), codec=fixture_codec))
    else:
        path.write_bytes(b"x" * 32769)
    with pytest.raises(TransferUnavailable):
        port.read()
    assert port.present() is (fault != "missing")


@pytest.mark.parametrize("stage", ["sync", "link", "after-link"])
def test_publication_failure_never_overwrites_and_retains_visible_fence(tmp_path, monkeypatch, stage):
    value = fence()
    port = ProtectedSourceTransfer(ProtectedConversationRestrictions(tmp_path, value.workspace_id, codec=fixture_codec))
    original = os.link
    if stage == "sync":
        monkeypatch.setattr(os, "fsync", lambda *args: (_ for _ in ()).throw(OSError()))
    else:
        def link(*args):
            if stage == "after-link":
                original(*args)
            raise OSError()
        monkeypatch.setattr(os, "link", link)
    with pytest.raises(TransferUnavailable):
        port.seal(value)
    assert port.present() is (stage == "after-link")
    if port.present():
        assert port.read() == value


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI source fence")
def test_actual_dpapi_fence(tmp_path):
    value = fence()
    port = ProtectedSourceTransfer(ProtectedConversationRestrictions(tmp_path, value.workspace_id))
    port.seal(value)
    assert b"root_binding" not in (tmp_path / FILE_NAME).read_bytes()
    assert port.read() == value


def _crash_child(root, value, during_link):
    port = ProtectedSourceTransfer(ProtectedConversationRestrictions(root, value.workspace_id, codec=fixture_codec))
    if during_link:
        original = os.link
        def crash_link(*args):
            original(*args)
            os._exit(0)
        os.link = crash_link
    port.seal(value)
    os._exit(0)


@pytest.mark.parametrize("during_link", [False, True])
def test_actual_child_exit_never_removes_visible_fence_or_keeps_lock(tmp_path, during_link):
    value = fence()
    restrictions = ProtectedConversationRestrictions(tmp_path, value.workspace_id, codec=fixture_codec)
    port = ProtectedSourceTransfer(restrictions)
    process = multiprocessing.get_context("spawn").Process(target=_crash_child, args=(tmp_path, value, during_link))
    try:
        process.start()
        process.join(timeout=15)
        assert process.exitcode == 0 and port.present()
        with restrictions._locked():
            pass  # The exited child cannot retain the kernel lock.
        if during_link:
            with pytest.raises(TransferUnavailable):
                port.read()  # Retained temporary hard link, never auto-repaired.
        else:
            assert port.read() == value
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        process.close()


def test_real_v2_offline_compatibility_and_rehashed_v3_frozen_fields_rejected(tmp_path):
    from test_conversation_exit import sample, rehash
    from class_os.domain.conversation_exit import validate_v2
    from class_os.domain.conversation_exit_v3 import build_package, validate_v3
    old = sample()
    path = tmp_path / "old-v2.json"
    path.write_bytes(rfc8785.dumps(old))
    verifier = Path(__file__).resolve().parents[1] / "verify_exit.py"
    result = subprocess.run([sys.executable, str(verifier), str(path), "--profile", "conversation-v2"],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and json.loads(result.stdout)["valid_synthetic_conversation"] is True
    conversations = deepcopy(old["conversations"])
    conversations["conversation_control"][0].update(transfer_id=None, transfer_hash=None, transfer_at=None)
    new = build_package(UUID(old["workspace_id"]), UUID(old["actor_refs"][0]), datetime.fromisoformat(old["created_at"]),
                        old["core"], conversations, old["restriction_evidence"], old["audit_refs"])
    assert len(validate_v3(new)) == 13
    with pytest.raises(ValueError):
        validate_v2(new)
    for values in ({"transfer_id": str(uuid4())}, {"transfer_hash": "a" * 64}, {"transfer_at": old["created_at"]}, {"activate": True}):
        changed = deepcopy(new)
        changed["conversations"]["conversation_control"][0].update(values)
        rehash(changed)
        with pytest.raises(ValueError):
            validate_v3(changed)
