"""Fixed historical results, not executable drafts or offline admission."""
from copy import deepcopy
from types import MappingProxyType

import rfc8785

from .conversation_exit import CONVERSATION_KEYS as OLD_KEYS, MAX_BYTES, _uuid, _instant
from .conversation_exit_v3 import CONVERSATION_COLUMNS as OLD_COLUMNS
from .conversation_exit_v4 import snapshot_hash as legacy_hash
from .conversation_exit_v5 import build_package as build_v5, validate_v5
from .conversation_result_integrity import validate_result_rows, message_key
from .conversation_results import RESULT_COLUMNS, RESULT_KEYS, QuerySource, ProducedResult, FinishResult
from .conversation_worker import FinishRun
from .durable_conversation import ConversationScope, SendIntent
from .activity import CreateTask
from .exit_package import checksum
from .recovery_results import legacy_recovery, validate_result_provenance


SCHEMA = "classmatter.synthetic-exit.v6"
CONVERSATION_COLUMNS = MappingProxyType({**OLD_COLUMNS, **RESULT_COLUMNS})
CONVERSATION_KEYS = MappingProxyType({**OLD_KEYS, **RESULT_KEYS})


def snapshot_hash(core, conversations, proof, recovery):
    # Only exact empty extra collections preserve an already committed legacy
    # hash. Any nonempty result rows remain inside the current full hash.
    projected = {kind: rows for kind, rows in conversations.items()
                 if kind not in RESULT_COLUMNS or type(rows) is not list or rows}
    return legacy_hash(core, projected, proof, recovery)


def _old_bundle(bundle):
    projected = deepcopy(bundle)
    projected.update(schema_version="classmatter.synthetic-exit.v5", source_revision="0023",
        conversations={key: projected["conversations"][key] for key in OLD_COLUMNS},
        recovery=legacy_recovery(projected["recovery"]))
    projected["snapshot_hash"] = legacy_hash(projected["core"], projected["conversations"], projected["restriction_evidence"], projected["recovery"])
    projected["package_checksum"] = checksum({key: value for key, value in projected.items() if key != "package_checksum"})
    return projected


def build_package(workspace, actor, now, core, conversations, proof, audit, recovery, *, verify_receipts=True):
    full = {**{key: [] for key in RESULT_COLUMNS}, **conversations}
    legacy = {key: full[key] for key in OLD_COLUMNS}
    bundle = build_v5(workspace, actor, now, core, legacy, proof, audit, legacy_recovery(recovery))
    bundle.update(schema_version=SCHEMA, source_revision="0026", conversations=full, recovery=recovery,
                  snapshot_hash=snapshot_hash(core, full, proof, recovery))
    bundle["package_checksum"] = checksum({key: value for key, value in bundle.items() if key != "package_checksum"})
    validate_v6(bundle, verify_receipts=verify_receipts)
    return bundle


def validate_v6(bundle, *, require_complete=False, verify_receipts=True):
    try:
        if (type(bundle) is not dict or bundle.get("schema_version") != SCHEMA or bundle.get("source_revision") != "0026"
                or len(rfc8785.dumps(bundle)) > MAX_BYTES
                or set(bundle["conversations"]) != set(CONVERSATION_COLUMNS)
                or bundle["package_checksum"] != checksum({key: value for key, value in bundle.items() if key != "package_checksum"})
                or bundle["snapshot_hash"] != snapshot_hash(bundle["core"], bundle["conversations"], bundle["restriction_evidence"], bundle["recovery"])):
            raise ValueError()
        # Check the actual FULL registry before any private old projection.
        validate_result_provenance(bundle["core"], bundle["conversations"], bundle["recovery"])
        counts = validate_v5(_old_bundle(bundle), require_complete=require_complete)
        groups = validate_result_rows(bundle["conversations"], bundle["workspace_id"], bundle["created_at"])
        verify_outcomes(bundle, groups, verify_receipts=verify_receipts)
        counts.update({kind: len(bundle["conversations"][kind]) for kind in RESULT_COLUMNS})
        return counts
    except Exception:
        raise ValueError("Invalid synthetic v6 historical results; no offline activation") from None


def source_context(bundle, thread, message):
    recovery = bundle["recovery"]
    imported = any(row["entity_kind"] == "conversation_message" and row["resource_id"] == message["message_id"]
                   and row["thread_id"] == message["thread_id"] for row in recovery["conversation_provenance"])
    if imported:
        batch, = recovery["conversation_import"]
        workspace, owner = batch["source_workspace_id"], batch["source_owner_id"]
        audit = [{**row, "workspace_id": row["source_workspace_id"]} for row in recovery["conversation_source_audit"]]
    else:
        workspace, owner, audit = bundle["workspace_id"], bundle["actor_refs"][0], bundle["audit_refs"]
    scope = ConversationScope(_uuid(workspace), _uuid(owner), _uuid(thread["class_id"]), _uuid(thread["term_id"]),
                              _uuid(thread["student_id"]) if thread["student_id"] is not None else None)
    return scope, audit, imported


def result_value(thread, message, group):
    sources = tuple(QuerySource(_uuid(row["source_id"]), _uuid(row["source_workspace_id"]), _uuid(row["source_owner_id"]),
                                _uuid(row["receipt_id"]), row["projection_hash"], _instant(row["as_of"])) for row in group["sources"])
    row = group["draft"]
    draft = CreateTask("task.create", _uuid(row["draft_id"]), _uuid(thread["class_id"]), _uuid(thread["term_id"]), row["title"]) if row else None
    return ProducedResult(message["body"], sources, draft)


def finish_command(thread, run, result=None, *, legacy_body=None, result_hash=None, legacy_hash=None):
    args = (_uuid(thread["thread_id"]), _uuid(thread["class_id"]), _uuid(thread["term_id"]), _uuid(run["run_id"]),
            run["version"] - 1, _uuid(run["generation"]))
    metrics = (run["duration_ms"], run["input_tokens"], run["output_tokens"])
    if result is None and result_hash is None:
        return FinishRun(*args, "completed", legacy_hash if legacy_hash is not None else checksum(legacy_body), *metrics)
    return FinishResult(*args, result.result_hash if result is not None else result_hash, *metrics)


def verify_outcomes(bundle, groups, *, verify_receipts):
    conversations = bundle["conversations"]
    threads = {row["thread_id"]: row for row in conversations["conversation_thread"]}
    turns = {(row["thread_id"], row["turn_id"]): row for row in conversations["conversation_turn"]}
    messages = {(row["thread_id"], row["turn_id"], row["role"]): row for row in conversations["conversation_message"]}
    for run in conversations["conversation_run"]:
        if run["state"] != "completed":
            continue
        message = messages[run["thread_id"], run["turn_id"], "assistant"]
        thread = threads[run["thread_id"]]
        turn = turns[run["thread_id"], run["turn_id"]]
        group = groups.get(message_key(message), {"sources": [], "draft": None, "receipt": None})
        scope, audit, imported = source_context(bundle, thread, message)
        # A live precommit structural projection has no final local audit yet.
        # Imported audit is already fixed source evidence and is always checked.
        if not verify_receipts and not imported:
            continue
        for source in group["sources"]:
            matches = [row for row in audit if row["event_id"] == source["receipt_id"] and row["workspace_id"] == source["source_workspace_id"]
                and row["actor_id"] == source["source_owner_id"] and row["action"] == "activity.today" and row["outcome"] == "allowed"
                and row["purpose"] == "manage-class" and row["class_id"] == thread["class_id"] and row["term_id"] == thread["term_id"]
                and row["resource_id"] == (thread["student_id"] or thread["class_id"]) and row["payload_hash"] == source["projection_hash"]
                and row["occurred_at"] == source["as_of"] and type(row["resource_version"]) is int and row["resource_version"] > 0]
            if len(matches) != 1 or source["source_workspace_id"] != str(scope.workspace_id) or source["source_owner_id"] != str(scope.owner_id):
                raise ValueError("Missing original historical query evidence")
        commits = [row for row in audit if row["workspace_id"] == str(scope.workspace_id) and row["actor_id"] == str(scope.owner_id)
            and row["action"] == "command.commit" and row["outcome"] == "allowed" and row["purpose"] == "manage-conversation"
            and row["resource_id"] == run["run_id"] and row["resource_version"] == run["version"] and row["occurred_at"] == run["ended_at"]
            and row["proposal_id"] is not None and row["receipt_id"] is not None
            and row["class_id"] == thread["class_id"] and row["term_id"] == thread["term_id"]]
        if group["receipt"] is not None:
            header = group["receipt"]
            command = finish_command(thread, run, legacy_hash=header["text_hash"]) if header["protocol"] == "legacy-plain" else finish_command(thread, run, result_hash=header["result_hash"])
            expected = checksum(command.canonical())
            if len(commits) != 1 or commits[0]["payload_hash"] != expected:
                raise ValueError("Missing full original result commit evidence")
            if message["visibility"] != "visible" or header["protocol"] == "legacy-plain":
                continue  # Digest-only full metadata verified even after clear.
        elif message["visibility"] != "visible":
            raise ValueError("Missing classified cleared completion receipt; legacy formats are not widened")
        legacy_hash = checksum(finish_command(thread, run, legacy_body=message["body"]).canonical())
        if not group["sources"] and group["draft"] is None and len(commits) == 1 and commits[0]["payload_hash"] == legacy_hash:
            continue  # Genuine old unstructured output, never a typed draft/source.
        result = result_value(thread, message, group)
        user = messages[run["thread_id"], run["turn_id"], "user"]
        intent = SendIntent(scope, _uuid(thread["thread_id"]), _uuid(turn["client_request_id"]), user["body"], turn["mode"], turn["draft_kind"])
        result.validate_intent(intent)
        expected = checksum(finish_command(thread, run, result).canonical())
        if len([row for row in commits if row["payload_hash"] == expected]) != 1:
            raise ValueError("Missing full original result commit evidence")
