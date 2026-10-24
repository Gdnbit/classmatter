"""Disposable local metadata only. Fixture codec is NOT encryption evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import multiprocessing
import os
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
import rfc8785

from class_os.infrastructure import conversation_restrictions as module
from class_os.infrastructure.conversation_restrictions import (
    ClearMarker, FILE_NAME, LOCK_NAME, ProtectedConversationRestrictions,
    RestrictionHead, RestrictionUnavailable,
)
from test_model_secrets import fixture_codec


NOW = datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def control(tmp_path):
    return ProtectedConversationRestrictions(tmp_path, uuid4(), codec=fixture_codec)


def marker(*, after=2, at=NOW):
    return ClearMarker(uuid4(), after, at)


def rewrite(control, mutate):
    path = control.root / FILE_NAME
    packet = json.loads(fixture_codec(path.read_bytes(), decrypt=True))
    mutate(packet)
    path.write_bytes(fixture_codec(rfc8785.dumps(packet)))


def test_explicit_initialization_restart_and_append_without_business_authority(control):
    head = control.initialize(uuid4())
    assert head.epoch == 0 and control.read().markers == ()
    first, second = marker(), marker(after=12, at=NOW + timedelta(seconds=1))
    next_head = control.advance(head, first)
    reopened = ProtectedConversationRestrictions(control.root, control.workspace_id, codec=fixture_codec)
    assert reopened.read().head == next_head
    assert reopened.require_current(next_head) == next_head
    assert reopened.compare(head).state == "one-ahead"
    assert reopened.compare(head).pending == first
    # A file ahead of a rolled-back DB is restrictive, never read permission.
    with pytest.raises(RestrictionUnavailable):
        reopened.require_current(head)
    final = reopened.advance(next_head, second)
    assert final.epoch == 2
    assert reopened.read().markers == (first, second)
    with pytest.raises(RestrictionUnavailable):
        reopened.compare(head)


def test_never_reinitialize_overwrite_or_implicitly_create_missing_control(control):
    with pytest.raises(RestrictionUnavailable):
        control.read()
    assert not (control.root / FILE_NAME).exists()
    head = control.initialize(uuid4())
    original = (control.root / FILE_NAME).read_bytes()
    with pytest.raises(RestrictionUnavailable):
        control.initialize(uuid4())
    assert (control.root / FILE_NAME).read_bytes() == original
    (control.root / FILE_NAME).unlink()  # Owned fixture simulates lost control.
    for operation in (lambda: control.read(), lambda: control.require_current(head),
                      lambda: control.advance(head, marker())):
        with pytest.raises(RestrictionUnavailable):
            operation()
    assert not (control.root / FILE_NAME).exists()


def test_stale_foreign_ahead_and_altered_head_cannot_advance_or_release(control):
    head = control.initialize(uuid4())
    following = control.advance(head, marker())
    original = (control.root / FILE_NAME).read_bytes()
    invalid = [head, replace(following, authority_id=uuid4()), replace(following, workspace_id=uuid4()),
               replace(following, digest="f" * 64), replace(following, epoch=2)]
    for candidate in invalid:
        with pytest.raises(RestrictionUnavailable):
            control.advance(candidate, marker())
        with pytest.raises(RestrictionUnavailable):
            control.require_current(candidate)
    assert (control.root / FILE_NAME).read_bytes() == original


def test_duplicate_thread_clock_reversal_and_entry_limit_rejected(control, monkeypatch):
    monkeypatch.setattr(module, "MAX_ENTRIES", 2)
    first = marker()
    head = control.advance(control.initialize(uuid4()), first)
    before = (control.root / FILE_NAME).read_bytes()
    for candidate in (first, marker(at=NOW - timedelta(microseconds=1))):
        with pytest.raises(RestrictionUnavailable):
            control.advance(head, candidate)
        assert (control.root / FILE_NAME).read_bytes() == before
    head = control.advance(head, marker())
    with pytest.raises(RestrictionUnavailable):
        control.advance(head, marker())
    assert len(control.read().markers) == 2


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(unknown="not-accepted"),
    lambda p: p.update(schema_version="unknown"),
    lambda p: p.update(workspace_id=str(uuid4())),
    lambda p: p.update(root_binding="0" * 64),
    lambda p: p.update(authority_id=True),
    lambda p: p.update(entries={}),
    lambda p: p["entries"][0].update(unknown="not-accepted"),
    lambda p: p["entries"][0].update(thread_id="not-a-uuid"),
    lambda p: p["entries"][0].update(version_after=True),
    lambda p: p["entries"][0].update(version_after=1),
    lambda p: p["entries"][0].update(restricted_at="2026-10-24T01:00:00"),
    lambda p: p["entries"].append(p["entries"][0].copy()),
])
def test_closed_packet_rejects_untrusted_metadata(control, mutation):
    head = control.advance(control.initialize(uuid4()), marker())
    rewrite(control, mutation)
    with pytest.raises(RestrictionUnavailable):
        control.require_current(head)


def test_cross_root_and_workspace_copies_are_not_current_proof(control, tmp_path):
    head = control.initialize(uuid4())
    other = tmp_path / "other-runtime"
    other.mkdir()
    shutil.copyfile(control.root / FILE_NAME, other / FILE_NAME)
    for candidate in (ProtectedConversationRestrictions(other, control.workspace_id, codec=fixture_codec),
                      ProtectedConversationRestrictions(control.root, uuid4(), codec=fixture_codec)):
        with pytest.raises(RestrictionUnavailable):
            candidate.require_current(head)
    assert control.require_current(head) == head


@pytest.mark.parametrize("plain", [b"{}", b"[]", b"\xff", b'{"entries":[],"entries":[]}', b"NaN"])
def test_corrupt_duplicate_unknown_and_non_utf8_packets_rejected(control, plain):
    head = control.initialize(uuid4())
    (control.root / FILE_NAME).write_bytes(fixture_codec(plain))
    with pytest.raises(RestrictionUnavailable) as error:
        control.require_current(head)
    assert str(control.root) not in str(error.value)
    assert "no history release authorized" in str(error.value)


def test_noncanonical_oversized_and_time_reversal_packets_rejected(control, monkeypatch):
    head = control.initialize(uuid4())
    path = control.root / FILE_NAME
    original = path.read_bytes()
    plain = fixture_codec(original, decrypt=True)
    path.write_bytes(fixture_codec(b" " + plain))
    with pytest.raises(RestrictionUnavailable):
        control.read()
    path.write_bytes(original)
    monkeypatch.setattr(module, "SEALED_LIMIT", len(original) - 1)
    with pytest.raises(RestrictionUnavailable):
        control.read()
    monkeypatch.setattr(module, "SEALED_LIMIT", 2 * 1024 * 1024)
    monkeypatch.setattr(module, "PLAIN_LIMIT", len(plain) - 1)
    with pytest.raises(RestrictionUnavailable):
        control.read()
    monkeypatch.setattr(module, "PLAIN_LIMIT", 1024 * 1024)
    head = control.advance(head, marker())
    control.advance(head, marker(at=NOW + timedelta(seconds=1)))
    rewrite(control, lambda p: p["entries"][1].update(restricted_at=(NOW - timedelta(seconds=1)).isoformat()))
    with pytest.raises(RestrictionUnavailable):
        control.read()


@pytest.mark.parametrize("phase", ["codec", "fsync", "replace-before", "replace-after"])
def test_publication_failures_do_not_fake_success_or_undo_restriction(control, monkeypatch, phase):
    head = control.initialize(uuid4())
    original = (control.root / FILE_NAME).read_bytes()
    proposed = marker()
    replace_file = module.os.replace
    def fail(*args, **kwargs):
        raise OSError("synthetic publication failure")
    def replaced_then_fail(*args):
        replace_file(*args)
        fail()
    with monkeypatch.context() as patch:
        if phase == "codec":
            patch.setattr(control, "codec", lambda value, decrypt=False: fixture_codec(value, decrypt=True) if decrypt else fail())
        elif phase == "fsync":
            patch.setattr(module.os, "fsync", fail)
        else:
            patch.setattr(module.os, "replace", replaced_then_fail if phase == "replace-after" else fail)
        with pytest.raises(RestrictionUnavailable):
            control.advance(head, proposed)
    assert not tuple(control.root.glob(".restriction-*.pending"))
    if phase == "replace-after":
        assert control.read().markers == (proposed,)
        assert control.compare(head).state == "one-ahead"
        with pytest.raises(RestrictionUnavailable):
            control.require_current(head)
        with pytest.raises(RestrictionUnavailable):
            control.advance(head, proposed)
    else:
        assert (control.root / FILE_NAME).read_bytes() == original
        assert control.require_current(head) == head


def test_initial_collision_cannot_replace_existing_bytes(control, monkeypatch):
    original_link = module.os.link
    path = control.root / FILE_NAME
    def collide(source, destination):
        path.write_bytes(b"synthetic-existing-authority")
        return original_link(source, destination)
    monkeypatch.setattr(module.os, "link", collide)
    with pytest.raises(RestrictionUnavailable):
        control.initialize(uuid4())
    assert path.read_bytes() == b"synthetic-existing-authority"
    assert not tuple(control.root.glob(".restriction-*.pending"))


def test_missing_root_and_nonregular_control_or_lock_refused(control, tmp_path):
    with pytest.raises(ValueError):
        ProtectedConversationRestrictions(Path("relative"), uuid4())
    absent = ProtectedConversationRestrictions(tmp_path / "absent", uuid4(), codec=fixture_codec)
    with pytest.raises(RestrictionUnavailable):
        absent.initialize(uuid4())
    assert not absent.root.exists()
    for name in (FILE_NAME, LOCK_NAME):
        path = control.root / name
        if path.exists():
            path.unlink()
        path.mkdir()
        with pytest.raises(RestrictionUnavailable):
            control.initialize(uuid4())
        path.rmdir()


def test_linked_root_is_refused(control, tmp_path):
    head = control.initialize(uuid4())
    alias = tmp_path / "linked-root"
    try:
        alias.symlink_to(control.root, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit fixture symlinks")
    with pytest.raises(RestrictionUnavailable):
        ProtectedConversationRestrictions(alias, control.workspace_id, codec=fixture_codec).read()
    alias.unlink()


def test_hardlinked_control_and_lock_are_refused(control, tmp_path):
    head = control.initialize(uuid4())
    for name in (FILE_NAME, LOCK_NAME):
        original = control.root / name
        linked = tmp_path / ("extra-" + name)
        os.link(original, linked)
        with pytest.raises(RestrictionUnavailable):
            control.require_current(head)
        linked.unlink()
    assert control.require_current(head) == head


def test_file_and_lock_symlinks_are_refused(control, tmp_path):
    head = control.initialize(uuid4())
    for name in (FILE_NAME, LOCK_NAME):
        path = control.root / name
        saved = tmp_path / ("saved-" + name)
        path.rename(saved)
        try:
            path.symlink_to(saved)
        except OSError:
            saved.rename(path)
            pytest.skip("Host does not permit fixture symlinks")
        try:
            with pytest.raises(RestrictionUnavailable):
                control.require_current(head)
        finally:
            path.unlink()
            saved.rename(path)


def test_unlock_failure_still_closes_descriptor(control, monkeypatch):
    head = control.initialize(uuid4())
    closed = []
    original_close = module.os.close
    def close(descriptor):
        closed.append(descriptor)
        return original_close(descriptor)
    if os.name == "nt":
        import msvcrt
        original_lock = msvcrt.locking
        def lock(descriptor, mode, count):
            if mode == msvcrt.LK_UNLCK:
                raise OSError("synthetic unlock failure")
            return original_lock(descriptor, mode, count)
        target, method = msvcrt, "locking"
    else:
        import fcntl
        original_lock = fcntl.flock
        def lock(descriptor, mode):
            if mode == fcntl.LOCK_UN:
                raise OSError("synthetic unlock failure")
            return original_lock(descriptor, mode)
        target, method = fcntl, "flock"
    with monkeypatch.context() as patch:
        patch.setattr(module.os, "close", close)
        patch.setattr(target, method, lock)
        with pytest.raises(RestrictionUnavailable):
            control.require_current(head)
    assert closed
    assert control.require_current(head) == head


def _advance_worker(root, workspace_id, expected, candidate, barrier, results):
    control = ProtectedConversationRestrictions(root, workspace_id, codec=fixture_codec)
    barrier.wait(timeout=15)
    try:
        control.advance(expected, candidate)
        results.put("advanced")
    except RestrictionUnavailable:
        results.put("refused")


def _exit_while_locked(root, workspace_id):
    control = ProtectedConversationRestrictions(root, workspace_id, codec=fixture_codec)
    with control._locked():
        os._exit(0)  # Fixture child only: deliberately bypass Python finally.


def test_process_exit_releases_kernel_lock_without_resetting_evidence(control):
    head = control.advance(control.initialize(uuid4()), marker())
    before = (control.root / FILE_NAME).read_bytes()
    process = multiprocessing.get_context("spawn").Process(target=_exit_while_locked,
                                                           args=(control.root, control.workspace_id))
    try:
        process.start()
        process.join(timeout=15)
        assert process.exitcode == 0
        assert (control.root / FILE_NAME).read_bytes() == before
        assert control.require_current(head) == head
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)


def test_cross_process_expected_head_only_one_winner(control):
    head = control.initialize(uuid4())
    context = multiprocessing.get_context("spawn")
    barrier, results = context.Barrier(3), context.Queue()
    processes = [context.Process(target=_advance_worker, args=(control.root, control.workspace_id, head,
                                                              marker(), barrier, results)) for _ in range(2)]
    try:
        for process in processes:
            process.start()
        barrier.wait(timeout=15)
        received = [results.get(timeout=20), results.get(timeout=20)]
        assert sorted(received) == ["advanced", "refused"]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert control.read().head.epoch == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()
        results.join_thread()


def test_busy_lock_fails_closed_and_releases_on_exception(control):
    head = control.initialize(uuid4())
    with control._locked():
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(control.require_current, head)
            with pytest.raises(RestrictionUnavailable):
                future.result(timeout=5)
    assert control.require_current(head) == head
    with pytest.raises(RuntimeError):
        with control._locked():
            raise RuntimeError("synthetic application abort")
    assert control.require_current(head) == head


@pytest.mark.parametrize("bad", [True, -1, 0, 1, 2147483648, "2"])
def test_marker_rejects_bool_unbounded_or_nonversion_values(bad):
    with pytest.raises(ValueError):
        marker(after=bad)


def test_closed_types_and_utc_times(control):
    with pytest.raises(ValueError):
        ClearMarker(str(uuid4()), 2, NOW)
    for at in (NOW.replace(tzinfo=None), NOW.astimezone(timezone(timedelta(hours=8))), "now"):
        with pytest.raises(ValueError):
            marker(at=at)
    for epoch, digest in ((True, "0" * 64), (-1, "0" * 64), (0, "F" * 64), (0, "x")):
        with pytest.raises(ValueError):
            RestrictionHead(uuid4(), uuid4(), epoch, digest)
    with pytest.raises(RestrictionUnavailable):
        control.initialize("not-a-uuid")
    head = control.initialize(uuid4())
    with pytest.raises(RestrictionUnavailable):
        control.advance(head, {"thread_id": str(uuid4())})
    with pytest.raises(RestrictionUnavailable):
        control.compare({"digest": head.digest})


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows current-user DPAPI")
def test_actual_dpapi_protects_marker_and_detects_corruption(tmp_path):
    control = ProtectedConversationRestrictions(tmp_path, uuid4())
    head = control.initialize(uuid4())
    restricted = marker()
    head = control.advance(head, restricted)
    sealed = (tmp_path / FILE_NAME).read_bytes()
    assert str(restricted.thread_id).encode() not in sealed and KIND_BYTES not in sealed
    assert control.require_current(head) == head
    corrupted = bytearray(sealed)
    corrupted[len(corrupted) // 2] ^= 1
    (tmp_path / FILE_NAME).write_bytes(corrupted)
    with pytest.raises(RestrictionUnavailable):
        control.read()


KIND_BYTES = module.KIND.encode()
