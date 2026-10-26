"""Synthetic v2 schema/evidence tests, not authorization or recovery success."""
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from class_os.domain.conversation_exit import CONVERSATION_COLUMNS, CreateConversationExit, build_package, validate_v2, snapshot_hash
from class_os.domain.exit_package import checksum, validate_package
from class_os.domain.roster import decode
from class_os.infrastructure.persistence.schema_inventory import D1_COLUMNS
from test_exit_package import rich_package


def sample():
    old = rich_package()
    w, actor, at = old["workspace_id"], old["actor_refs"][0], old["created_at"]
    core = old["core"]
    classroom = core["school_class"][0]
    thread, turn, run = (str(uuid4()) for _ in range(3))
    authority = str(uuid4())
    collections = {key: [] for key in CONVERSATION_COLUMNS}
    collections["conversation_thread"] = [{"workspace_id": w, "thread_id": thread, "owner_id": actor,
        "class_id": classroom["class_id"], "term_id": classroom["term_id"], "student_id": None, "enrollment_id": None,
        "title": "合成班务历史", "status": "active", "version": 1, "created_at": at, "updated_at": at, "cleared_at": None}]
    collections["conversation_turn"] = [{"workspace_id": w, "thread_id": thread, "turn_id": turn, "ordinal": 1,
        "client_request_id": str(uuid4()), "request_hash": "a" * 64, "mode": "read", "draft_kind": "task", "created_at": at}]
    collections["conversation_message"] = [{"workspace_id": w, "thread_id": thread, "turn_id": turn, "message_id": str(uuid4()),
        "role": "user", "origin": "user-original", "visibility": "visible", "body": "合成用户原文", "created_at": at}]
    collections["conversation_run"] = [{"workspace_id": w, "thread_id": thread, "turn_id": turn, "run_id": run,
        "state": "queued", "version": 1, "created_at": at, "queued_until": (datetime.fromisoformat(at) + timedelta(minutes=1)).isoformat(),
        "generation": None, "started_at": None, "lease_until": None, "ended_at": None, "cancel_requested_at": None,
        "input_tokens": None, "output_tokens": None, "duration_ms": None}]
    collections["conversation_control"] = [{"workspace_id": w, "owner_id": actor, "authority_id": authority,
        "epoch": 0, "head_hash": "b" * 64, "created_at": at, "updated_at": at}]
    proof = {"authority_id": authority, "epoch": 0, "source_head_hash": "b" * 64, "markers": []}
    return build_package(w, actor, datetime.fromisoformat(at), core, collections, proof, [])


def rehash(bundle):
    bundle["snapshot_hash"] = snapshot_hash(bundle["core"], bundle["conversations"], bundle["restriction_evidence"])
    bundle["package_checksum"] = checksum({key: value for key, value in bundle.items() if key != "package_checksum"})


def test_thirteen_legacy_collections_stay_exact_subset_of_current_d1_without_authority():
    bundle = sample()
    assert len(validate_v2(bundle)) == 13
    from class_os.domain.conversation_exit_v6 import CONVERSATION_COLUMNS as CURRENT_COLUMNS
    from class_os.domain.target_import import IMPORT_COLUMNS
    from class_os.domain.recovery_admission import ADMISSION_COLUMNS
    assert {key: set(columns) for key, columns in {**CURRENT_COLUMNS, **IMPORT_COLUMNS, **ADMISSION_COLUMNS}.items()} == dict(D1_COLUMNS)
    assert set(CONVERSATION_COLUMNS["conversation_control"]) < D1_COLUMNS["conversation_control"]
    assert bundle["conversations"]["conversation_run"][0]["state"] == "queued"
    assert bundle["activation_allowed"] is False and bundle["run_authority"] == "source-evidence-only"
    with pytest.raises(ValueError):
        validate_package(bundle)
    with pytest.raises(ValueError):
        validate_v2(bundle, require_complete=True)
    command = CreateConversationExit(uuid4(), bundle["snapshot_hash"])
    with pytest.raises(ValueError):
        decode(command.canonical())


def test_unknown_command_is_rejected_before_activity_scope_lookup():
    from class_os.application.activity import validate_activity
    class NoScopeReads:
        def class_context(self, *args):
            raise AssertionError("Unknown command must not perform a scope lookup")
    assert validate_activity(NoScopeReads(), {}, object(), None) is False


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(activation_allowed=True),
    lambda b: b.update(activation_allowed=0),
    lambda b: b.update(run_authority="dispatch"),
    lambda b: b.update(source_revision="0018"),
    lambda b: b["lifecycle_status"].update(complete=True),
    lambda b: b["core"]["workspace"][0].update(password_hash="not-portable"),
    lambda b: b["conversations"].update(sdk_session=[]),
    lambda b: b["conversations"].pop("conversation_control"),
    lambda b: b["conversations"]["conversation_control"][0].update(owner_id=str(uuid4())),
    lambda b: b["conversations"]["conversation_control"][0].update(epoch=True),
    lambda b: b["conversations"]["conversation_thread"][0].update(owner_id=str(uuid4())),
    lambda b: b["conversations"]["conversation_thread"][0].update(thread_id=None),
    lambda b: b["conversations"]["conversation_thread"][0].update(enrollment_id=str(uuid4())),
    lambda b: b["conversations"]["conversation_turn"][0].update(class_id=str(uuid4())),
    lambda b: b["conversations"]["conversation_turn"][0].update(thread_id=str(uuid4())),
    lambda b: b["conversations"]["conversation_turn"][0].update(ordinal=True),
    lambda b: b["conversations"]["conversation_message"][0].update(role="system"),
    lambda b: b["conversations"]["conversation_message"][0].update(origin="teacher-fact"),
    lambda b: b["conversations"]["conversation_message"][0].update(body="x" * 2001),
    lambda b: b["conversations"]["conversation_message"][0].update(visibility="restricted", body=None),
    lambda b: b["conversations"]["conversation_run"][0].update(generation=str(uuid4())),
    lambda b: b["conversations"]["conversation_run"][0].update(input_tokens=1),
    lambda b: b["conversations"]["conversation_run"].clear(),
    lambda b: b["conversations"]["conversation_turn"].append(deepcopy(b["conversations"]["conversation_turn"][0])),
    lambda b: b["restriction_evidence"].update(epoch=True),
    lambda b: b["restriction_evidence"].update(source_head_hash="0" * 64),
    lambda b: b["restriction_evidence"].update(root_path="not-portable"),
])
def test_rehashed_invalid_shape_source_scope_and_claims_rejected(mutation):
    bundle = sample()
    mutation(bundle)
    rehash(bundle)
    with pytest.raises(ValueError):
        validate_v2(bundle)


def test_cleared_data_requires_matching_marker_and_no_visible_body():
    bundle = sample()
    conversation = bundle["conversations"]
    thread = conversation["conversation_thread"][0]
    thread.update(status="cleared", title="已清除的会话", version=2, cleared_at=bundle["created_at"])
    conversation["conversation_message"][0].update(body=None, visibility="restricted")
    conversation["conversation_run"][0].update(state="cancelled", version=2, ended_at=bundle["created_at"])
    marker = {"thread_id": thread["thread_id"], "version_after": 2, "restricted_at": bundle["created_at"]}
    bundle["restriction_evidence"].update(epoch=1, markers=[marker])
    conversation["conversation_control"][0]["epoch"] = 1
    rehash(bundle)
    assert validate_v2(bundle)["conversation_message"] == 1
    for mutate in (lambda b: b["conversations"]["conversation_message"][0].update(body="合成旧正文", visibility="visible"),
                   lambda b: b["conversations"]["conversation_thread"][0].update(version=3),
                   lambda b: b["restriction_evidence"]["markers"].append(marker)):
        changed = deepcopy(bundle)
        mutate(changed)
        rehash(changed)
        with pytest.raises(ValueError):
            validate_v2(changed)


def test_orphan_clear_marker_is_rejected_even_after_rehash():
    bundle = sample()
    bundle["restriction_evidence"].update(epoch=1, markers=[{
        "thread_id": str(uuid4()), "version_after": 2, "restricted_at": bundle["created_at"]}])
    bundle["conversations"]["conversation_control"][0]["epoch"] = 1
    rehash(bundle)
    with pytest.raises(ValueError):
        validate_v2(bundle)


def test_valid_checksum_is_not_source_authentication_or_activation():
    bundle = sample()
    bundle["conversations"]["conversation_message"][0]["body"] = "合成篡改后仍符合类型"
    rehash(bundle)
    assert validate_v2(bundle)
    # Structural integrity cannot authenticate a caller who rewrites hashes.
    assert bundle["activation_allowed"] is False
