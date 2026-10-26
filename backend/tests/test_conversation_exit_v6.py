"""Fixed v6 format tests only, no source authentication or admission authority."""
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from class_os.domain.conversation_exit_v6 import build_package, validate_v6, snapshot_hash, finish_command, result_value
from class_os.domain.conversation_exit_v5 import validate_v5
from class_os.domain.conversation_results import RESULT_COLUMNS
from class_os.domain.exit_package import checksum, AUDIT_COLUMNS
from test_recovery_admission import sample as old_sample


def rehash(bundle):
    bundle["snapshot_hash"] = snapshot_hash(bundle["core"], bundle["conversations"], bundle["restriction_evidence"], bundle["recovery"])
    bundle["package_checksum"] = checksum({key: value for key, value in bundle.items() if key != "package_checksum"})


def sample(mode="read"):
    old = old_sample(admitted=False, imported=False)
    conversations = deepcopy(old["conversations"])
    conversations.update({key: [] for key in RESULT_COLUMNS})
    thread, turn, run = (conversations[kind][0] for kind in ("conversation_thread", "conversation_turn", "conversation_run"))
    begin = datetime.fromisoformat(old["created_at"])
    end = (begin + timedelta(seconds=1)).isoformat()
    turn["mode"] = mode
    thread["updated_at"] = end
    run.update(state="completed", version=3, generation=str(uuid4()), started_at=begin.isoformat(),
               lease_until=(begin+timedelta(minutes=1)).isoformat(), ended_at=end)
    message = {**conversations["conversation_message"][0], "message_id": str(uuid4()), "role": "assistant",
               "origin": "assistant-unverified", "body": "synthetic output", "created_at": end}
    conversations["conversation_message"].append(message)
    coords = {key: message[key] for key in ("workspace_id", "thread_id", "turn_id", "message_id")}
    audit = []
    if mode == "read":
        source = {**coords, "message_role": "assistant", "source_id": str(uuid4()), "ordinal": 1,
            "source_workspace_id": old["workspace_id"], "source_owner_id": old["actor_refs"][0], "receipt_id": str(uuid4()),
            "projection_hash": "d" * 64, "as_of": begin.isoformat(), "created_at": end}
        conversations["conversation_query_source"].append(source)
        row = {key: None for key in AUDIT_COLUMNS}
        row.update(workspace_id=old["workspace_id"], actor_id=old["actor_refs"][0], event_id=source["receipt_id"],
                   action="activity.today", purpose="manage-class", outcome="allowed", occurred_at=source["as_of"],
                   resource_id=thread["class_id"], resource_version=1, class_id=thread["class_id"], term_id=thread["term_id"], payload_hash=source["projection_hash"])
        audit.append(row)
    elif mode == "draft":
        conversations["conversation_task_draft"].append({**coords, "message_role": "assistant", "draft_id": str(uuid4()),
            "title": "synthetic candidate", "title_hash": checksum("synthetic candidate"), "visibility": "visible", "created_at": end})
    group = {"sources": conversations["conversation_query_source"],
             "draft": next(iter(conversations["conversation_task_draft"]), None)}
    result = result_value(thread, message, group)
    conversations["conversation_result_receipt"].append({**coords, "message_role": "assistant", "protocol": "fixed-result", "text_hash": checksum(message["body"]),
        "result_hash": result.result_hash, "created_at": end, "recorded_at": end})
    commit = {key: None for key in AUDIT_COLUMNS}
    commit.update(workspace_id=old["workspace_id"], actor_id=old["actor_refs"][0], event_id=str(uuid4()), action="command.commit",
        purpose="manage-conversation", outcome="allowed", occurred_at=end, proposal_id=str(uuid4()), receipt_id=str(uuid4()),
        resource_id=run["run_id"], resource_version=run["version"], class_id=thread["class_id"], term_id=thread["term_id"],
        payload_hash=checksum(finish_command(thread, run, result).canonical()))
    audit.append(commit)
    return build_package(UUID(old["workspace_id"]), UUID(old["actor_refs"][0]), datetime.fromisoformat(end), old["core"],
                         conversations, old["restriction_evidence"], audit, old["recovery"])


@pytest.mark.parametrize("mode", ["read", "draft", "chat"])
def test_v6_exact_results_are_not_old_format_or_offline_authority(mode):
    bundle = sample(mode)
    assert validate_v6(bundle) and not bundle["activation_allowed"]
    with pytest.raises(ValueError):
        validate_v5(bundle)


def test_empty_new_collections_keep_actual_legacy_snapshot_hash_and_origins():
    for old in (old_sample(admitted=False, imported=False), old_sample(admitted=False), old_sample()):
        bundle = build_package(UUID(old["workspace_id"]), UUID(old["actor_refs"][0]), datetime.fromisoformat(old["created_at"]),
            old["core"], old["conversations"], old["restriction_evidence"], old["audit_refs"], old["recovery"])
        assert validate_v6(bundle) and bundle["snapshot_hash"] == old["snapshot_hash"]
        assert bundle["recovery"] == old["recovery"]
        assert validate_v5(old)


@pytest.mark.parametrize("fault", ["source-owner", "query-audit", "whole-source-set", "source-extra", "body", "completion-hash", "completion-audit"])
def test_rehashed_incomplete_or_changed_outcome_never_passes(fault):
    bundle = sample()
    if fault == "source-owner":
        bundle["conversations"]["conversation_query_source"][0]["source_owner_id"] = str(uuid4())
    elif fault == "query-audit":
        bundle["audit_refs"][0]["payload_hash"] = "e" * 64
    elif fault == "whole-source-set":
        bundle["conversations"]["conversation_query_source"] = []
    elif fault == "source-extra":
        bundle["conversations"]["conversation_query_source"][0]["arbitrary_json"] = {}
    elif fault == "body":
        bundle["conversations"]["conversation_message"][-1]["body"] = "synthetic replaced output"
    elif fault == "completion-hash":
        bundle["audit_refs"][-1]["payload_hash"] = "e" * 64
    else:
        bundle["audit_refs"].pop()
    rehash(bundle)
    with pytest.raises(ValueError):
        validate_v6(bundle)


def test_deleted_entire_draft_cannot_downgrade_new_result_to_legacy():
    bundle = sample("draft")
    bundle["conversations"]["conversation_task_draft"] = []
    rehash(bundle)
    with pytest.raises(ValueError):
        validate_v6(bundle)


@pytest.mark.parametrize("mode", ["read", "draft", "chat"])
def test_deleting_result_and_all_commit_evidence_never_means_legacy(mode):
    bundle = sample(mode)
    for kind in RESULT_COLUMNS:
        bundle["conversations"][kind] = []
    bundle["audit_refs"] = []
    rehash(bundle)
    with pytest.raises(ValueError):
        validate_v6(bundle)


@pytest.mark.parametrize("mode", ["read", "draft", "chat"])
@pytest.mark.parametrize("fault", ["audit", "whole-result"])
def test_clear_keeps_digest_only_result_and_detects_removed_evidence(mode, fault):
    bundle = sample(mode)
    conversations = bundle["conversations"]
    thread = conversations["conversation_thread"][0]
    at = bundle["created_at"]
    thread.update(status="cleared", version=thread["version"]+1, cleared_at=at, title="已清除的会话")
    for row in conversations["conversation_message"]:
        row.update(body=None, visibility="restricted")
    for row in conversations["conversation_task_draft"]:
        row.update(title=None, visibility="restricted")
    # Fixed synthetic shape only; this does not mint a live protected witness.
    proof = bundle["restriction_evidence"]
    proof["markers"] = [{"thread_id": thread["thread_id"], "version_after": thread["version"], "restricted_at": at}]
    proof["epoch"] = 1
    proof["source_head_hash"] = "c" * 64
    conversations["conversation_control"][0].update(epoch=1, head_hash=proof["source_head_hash"], updated_at=at)
    rehash(bundle)
    assert validate_v6(bundle)
    if fault == "audit":
        bundle["audit_refs"] = []
    else:
        for kind in RESULT_COLUMNS:
            conversations[kind] = []
    rehash(bundle)
    with pytest.raises(ValueError):
        validate_v6(bundle)
