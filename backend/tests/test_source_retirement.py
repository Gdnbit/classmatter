"""Closed retirement proofs and owned append-once files, all synthetic."""
from dataclasses import replace
from datetime import timedelta
import multiprocessing
import os
from uuid import uuid4

import pytest

from class_os.domain.roster import decode
from class_os.domain.source_transfer import CommittedSource
from class_os.domain.target_import import TargetFence, StageConversationImport
from class_os.domain.source_retirement import (CommittedStage, RetireConversationSource, RetirementFence,
    decode_retirement, decode_retirement_fence, decode_stage)
from class_os.infrastructure.conversation_restrictions import ProtectedConversationRestrictions
from class_os.infrastructure.source_retirement import ProtectedSourceRetirement, RetirementUnavailable, FILE_NAME
from test_model_secrets import fixture_codec
from test_source_transfer import fence as source_fence


def evidence(root, *, codec=fixture_codec):
    source = source_fence()
    restrictions = ProtectedConversationRestrictions(root, source.workspace_id, codec=codec)
    binding = restrictions._binding(restrictions._root())
    source = replace(source, command=replace(source.command, target_binding="d" * 64))
    committed = CommittedSource(source, "e" * 64, uuid4(), binding)
    target = TargetFence(source.command.target_workspace_id, source.command.target_owner_id, uuid4(), "f" * 64,
                         StageConversationImport(source.command.attempt_id, source.command.package_hash, committed.fence_hash),
                         committed.receipt_id, source.created_at + timedelta(seconds=1))
    stage = CommittedStage(target, "1" * 64, uuid4(), source.command.target_binding, "2" * 64, target.created_at)
    command = RetireConversationSource(source.command.attempt_id, stage.snapshot_hash)
    return restrictions, RetirementFence(committed, stage, command, stage.imported_at + timedelta(seconds=1))


def test_closed_proof_and_command_never_admit_or_become_r1(tmp_path):
    _, value = evidence(tmp_path)
    assert decode_retirement(value.command.canonical()) == value.command
    assert decode_retirement_fence(value.canonical()) == value
    assert decode_stage(value.stage.canonical()) == value.stage
    with pytest.raises(ValueError):
        decode(value.command.canonical())
    for payload, parser in (({**value.command.canonical(), "admit": True}, decode_retirement),
                            ({**value.canonical(), "password": "not-real"}, decode_retirement_fence),
                            ({**value.stage.canonical(), "activation_allowed": True}, decode_stage)):
        with pytest.raises(ValueError):
            parser(payload)
    for fields in ({"attempt_id": uuid4()}, {"expected_stage_hash": "bad"}):
        with pytest.raises(ValueError):
            command = replace(value.command, **fields)
            replace(value, command=command)
    for stage in (replace(value.stage, root_binding="a" * 64),
                  replace(value.stage, fence=replace(value.stage.fence, source_receipt_id=uuid4())),
                  replace(value.stage, fence=replace(value.stage.fence, owner_id=uuid4()))):
        with pytest.raises(ValueError):
            replace(value, stage=stage)
    with pytest.raises(ValueError):
        replace(value, created_at=value.source.fence.created_at - timedelta(seconds=1))


def test_file_is_exclusive_idempotent_and_reopens(tmp_path):
    restrictions, value = evidence(tmp_path)
    port = ProtectedSourceRetirement(restrictions)
    assert not port.present()
    digest = port.retire(value)
    original = (tmp_path / FILE_NAME).read_bytes()
    assert port.read() == value and port.digest(value) == digest
    assert port.retire(value) == digest and (tmp_path / FILE_NAME).read_bytes() == original
    with pytest.raises(RetirementUnavailable):
        port.retire(replace(value, created_at=value.created_at + timedelta(seconds=1)))


@pytest.mark.parametrize("fault", ["missing", "corrupt", "directory", "hardlink", "copy-root", "wrong-workspace", "oversize"])
def test_uncertain_file_never_grants_retirement(tmp_path, fault):
    restrictions, value = evidence(tmp_path)
    port = ProtectedSourceRetirement(restrictions)
    port.retire(value)
    path = tmp_path / FILE_NAME
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"synthetic-corruption")
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    elif fault == "hardlink":
        os.link(path, tmp_path / "extra-link")
    elif fault == "copy-root":
        other = tmp_path / "foreign-root"
        other.mkdir()
        (other / FILE_NAME).write_bytes(path.read_bytes())
        port = ProtectedSourceRetirement(ProtectedConversationRestrictions(other, value.source.fence.workspace_id, codec=fixture_codec))
    elif fault == "wrong-workspace":
        port = ProtectedSourceRetirement(ProtectedConversationRestrictions(tmp_path, uuid4(), codec=fixture_codec))
    else:
        path.write_bytes(b"x" * 32769)
    with pytest.raises(RetirementUnavailable):
        port.read()


@pytest.mark.parametrize("stage", ["sync", "link", "after-link"])
def test_file_fault_preserves_visible_fence(tmp_path, monkeypatch, stage):
    restrictions, value = evidence(tmp_path)
    port = ProtectedSourceRetirement(restrictions)
    original = os.link
    if stage == "sync":
        monkeypatch.setattr(os, "fsync", lambda *args: (_ for _ in ()).throw(OSError()))
    else:
        def link(*args):
            if stage == "after-link":
                original(*args)
            raise OSError()
        monkeypatch.setattr(os, "link", link)
    with pytest.raises(RetirementUnavailable):
        port.retire(value)
    assert port.present() is (stage == "after-link")
    if port.present():
        assert port.read() == value


def _crash_child(root, value, during_link):
    port = ProtectedSourceRetirement(ProtectedConversationRestrictions(root, value.source.fence.workspace_id, codec=fixture_codec))
    if during_link:
        original = os.link
        def crash(*args):
            original(*args)
            os._exit(0)
        os.link = crash
    port.retire(value)
    os._exit(0)


@pytest.mark.parametrize("during_link", [False, True])
def test_actual_process_exit_keeps_fence_and_releases_lock(tmp_path, during_link):
    restrictions, value = evidence(tmp_path)
    child = multiprocessing.get_context("spawn").Process(target=_crash_child, args=(tmp_path, value, during_link))
    try:
        child.start()
        child.join(timeout=15)
        assert child.exitcode == 0
        port = ProtectedSourceRetirement(restrictions)
        assert port.present()
        with restrictions._locked():
            pass
        if during_link:
            with pytest.raises(RetirementUnavailable):
                port.read()
        else:
            assert port.read() == value
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
        child.close()


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows DPAPI")
def test_actual_dpapi_retirement(tmp_path):
    from class_os.infrastructure.local_runtime import protect
    restrictions, value = evidence(tmp_path, codec=protect)
    port = ProtectedSourceRetirement(restrictions)
    port.retire(value)
    assert b"source" not in (tmp_path / FILE_NAME).read_bytes()
    assert port.read() == value
