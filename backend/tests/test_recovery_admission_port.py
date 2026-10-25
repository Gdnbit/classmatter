"""Owned append-once admission evidence; no business admission in these tests."""
from dataclasses import replace
from datetime import timedelta
import multiprocessing
import os
from uuid import uuid4

import pytest

from class_os.domain.recovery_admission import AdmissionFence, AdmitConversationTarget
from class_os.domain.source_retirement import CommittedRetirement
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions
from class_os.infrastructure.recovery_admission import ProtectedTargetAdmission, AdmissionUnavailable, FILE_NAME
from test_model_secrets import fixture_codec
from test_source_retirement import evidence


def witness(root, *, codec=fixture_codec):
    (root / "source").mkdir()
    _, retired = evidence(root / "source")
    restrictions = ProtectedConversationRestrictions(root, retired.stage.fence.workspace_id, codec=codec)
    binding = restrictions._binding(restrictions._root())
    source = replace(retired.source, fence=replace(retired.source.fence,
        command=replace(retired.source.fence.command, target_binding=binding)))
    retired = replace(retired, source=source, stage=replace(retired.stage, root_binding=binding))
    proof = CommittedRetirement(retired, "a" * 64, uuid4())
    command = AdmitConversationTarget(retired.command.attempt_id, proof.proof_hash, retired.stage.snapshot_hash, "b" * 64)
    return restrictions, AdmissionFence(proof, command, 8, "c" * 64, "d" * 64, uuid4(), retired.created_at + timedelta(seconds=1))


def test_exclusive_idempotent_and_reopens(tmp_path):
    restrictions, fence = witness(tmp_path)
    port = ProtectedTargetAdmission(restrictions)
    assert not port.present()
    digest = port.publish(fence)
    original = (tmp_path / FILE_NAME).read_bytes()
    assert port.read() == fence and port.digest(fence) == digest
    assert port.publish(fence) == digest and (tmp_path / FILE_NAME).read_bytes() == original
    with pytest.raises(AdmissionUnavailable):
        port.publish(replace(fence, receipt_id=uuid4()))


@pytest.mark.parametrize("fault", ["missing", "corrupt", "directory", "hardlink", "copy-root", "workspace", "oversize"])
def test_uncertain_evidence_fails_closed(tmp_path, fault):
    restrictions, fence = witness(tmp_path)
    port = ProtectedTargetAdmission(restrictions)
    port.publish(fence)
    path = tmp_path / FILE_NAME
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"synthetic-corrupt")
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    elif fault == "hardlink":
        os.link(path, tmp_path / "duplicate")
    elif fault == "copy-root":
        other = tmp_path / "foreign"
        other.mkdir()
        (other / FILE_NAME).write_bytes(path.read_bytes())
        port = ProtectedTargetAdmission(ProtectedConversationRestrictions(other, fence.workspace_id, codec=fixture_codec))
    elif fault == "workspace":
        port = ProtectedTargetAdmission(ProtectedConversationRestrictions(tmp_path, uuid4(), codec=fixture_codec))
    else:
        path.write_bytes(b"x" * 32769)
    with pytest.raises(AdmissionUnavailable):
        port.read()


@pytest.mark.parametrize("fault", ["sync", "link", "after-link"])
def test_file_failure_never_overwrites_evidence(tmp_path, monkeypatch, fault):
    restrictions, fence = witness(tmp_path)
    port = ProtectedTargetAdmission(restrictions)
    original = os.link
    if fault == "sync":
        monkeypatch.setattr(os, "fsync", lambda *args: (_ for _ in ()).throw(OSError()))
    else:
        def link(*args):
            if fault == "after-link":
                original(*args)
            raise OSError()
        monkeypatch.setattr(os, "link", link)
    with pytest.raises(AdmissionUnavailable):
        port.publish(fence)
    assert port.present() is (fault == "after-link")
    if port.present():
        assert port.read() == fence


def crash_child(root, fence, during_link):
    port = ProtectedTargetAdmission(ProtectedConversationRestrictions(root, fence.workspace_id, codec=fixture_codec))
    if during_link:
        original = os.link
        def crash(*args):
            original(*args)
            os._exit(0)
        os.link = crash
    port.publish(fence)
    os._exit(0)


@pytest.mark.parametrize("during_link", [False, True])
def test_actual_process_exit_keeps_fence_and_releases_lock(tmp_path, during_link):
    restrictions, fence = witness(tmp_path)
    child = multiprocessing.get_context("spawn").Process(target=crash_child, args=(tmp_path, fence, during_link))
    try:
        child.start()
        child.join(timeout=15)
        assert child.exitcode == 0
        port = ProtectedTargetAdmission(restrictions)
        assert port.present()
        with restrictions._locked():
            pass
        if during_link:
            with pytest.raises(AdmissionUnavailable):
                port.read()
        else:
            assert port.read() == fence
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
        child.close()


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI")
def test_actual_dpapi(tmp_path):
    from class_os.infrastructure.local_runtime import protect
    restrictions, fence = witness(tmp_path, codec=protect)
    port = ProtectedTargetAdmission(restrictions)
    port.publish(fence)
    assert b"retirement" not in (tmp_path / FILE_NAME).read_bytes()
    assert port.read() == fence
