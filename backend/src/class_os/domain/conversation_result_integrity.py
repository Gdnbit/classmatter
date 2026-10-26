"""Fixed v6 result relations only, not QG evidence or recovery admission.

Callers must separately verify current restriction evidence, original complete
result receipt/hash and source audits. Presence alone must never classify an
old completed response as a new typed result or authorize a historical draft.
"""
from .conversation_exit import MAX_ROWS, _uuid, _hash, _instant
from .conversation_results import RESULT_COLUMNS, RESULT_ENTITY_KEYS, QuerySource, ProducedResult, result_canonical
from .activity import CreateTask
from .exit_package import checksum


def message_key(row):
    return row["workspace_id"], row["thread_id"], row["turn_id"], row["message_id"]


def validate_result_rows(conversations, workspace, now):
    """Return ordered fixed groups; no SQL, model call or authority is produced."""
    _uuid(workspace)
    at = _instant(now)
    messages = {message_key(row): row for row in conversations["conversation_message"]}
    runs = {(row["workspace_id"], row["thread_id"], row["turn_id"]): row for row in conversations["conversation_run"]}
    turns = {(row["workspace_id"], row["thread_id"], row["turn_id"]): row for row in conversations["conversation_turn"]}
    threads = {(row["workspace_id"], row["thread_id"]): row for row in conversations["conversation_thread"]}
    groups = {}
    for kind, columns in RESULT_COLUMNS.items():
        rows = conversations[kind]
        if type(rows) is not list or len(rows) > MAX_ROWS:
            raise ValueError("Unbounded result collection")
        seen = set()
        for row in rows:
            if type(row) is not dict or set(row) != set(columns) or row["workspace_id"] != workspace:
                raise ValueError("Unknown result scope/columns")
            for column in ("workspace_id", "thread_id", "turn_id", "message_id", RESULT_ENTITY_KEYS[kind]):
                _uuid(row[column])
            identity = row[RESULT_ENTITY_KEYS[kind]]
            if identity in seen:
                raise ValueError("Duplicate result identity")
            seen.add(identity)
            key = message_key(row)
            parent, run, turn = messages.get(key), runs.get(key[:3]), turns.get(key[:3])
            created = _instant(row["created_at"])
            if (parent is None or run is None or turn is None or row["message_role"] != "assistant"
                    or parent["role"] != "assistant" or parent["origin"] != "assistant-unverified"
                    or parent["visibility"] not in ("visible", "restricted")
                    or run["state"] != "completed" or created != _instant(parent["created_at"])
                    or created != _instant(run["ended_at"]) or created > at):
                raise ValueError("Result not bound to the completed assistant message")
            group = groups.setdefault(key, {"sources": [], "draft": None, "receipt": None})
            if kind == "conversation_result_receipt":
                _hash(row["text_hash"])
                _hash(row["result_hash"])
                if (group["receipt"] is not None or row["protocol"] not in ("legacy-plain", "fixed-result")
                        or not created <= _instant(row["recorded_at"]) <= at
                        or row["protocol"] == "fixed-result" and row["recorded_at"] != row["created_at"]):
                    raise ValueError("Duplicate result receipt")
                group["receipt"] = row
            elif kind == "conversation_query_source":
                source = QuerySource(_uuid(row["source_id"]), _uuid(row["source_workspace_id"]), _uuid(row["source_owner_id"]),
                                     _uuid(row["receipt_id"]), row["projection_hash"], _instant(row["as_of"]))
                if (turn["mode"] != "read" or type(row["ordinal"]) is not int or not 1 <= row["ordinal"] <= 2
                        or not _instant(run["started_at"]) <= source.as_of <= created):
                    raise ValueError("Query source outside this read/run window")
                group["sources"].append(row)
            else:
                thread = threads.get(key[:2])
                _hash(row["title_hash"])
                if (thread is None or thread["student_id"] is not None or turn["mode"] != "draft"
                        or turn["draft_kind"] != "task" or group["draft"] is not None
                        or row["visibility"] != parent["visibility"]):
                    raise ValueError("Draft mode, scope or visibility changed")
                if row["visibility"] == "visible":
                    CreateTask("task.create", _uuid(row["draft_id"]), _uuid(thread["class_id"]), _uuid(thread["term_id"]), row["title"])
                    if checksum(row["title"]) != row["title_hash"]:
                        raise ValueError("Draft content digest mismatch")
                elif row["visibility"] != "restricted" or row["title"] is not None:
                    raise ValueError("Cleared draft retained content")
                group["draft"] = row
    for key, group in groups.items():
        group["sources"].sort(key=lambda row: row["ordinal"])
        sources = group["sources"]
        receipt = group["receipt"]
        if receipt is None:
            raise ValueError("Missing fixed result receipt")
        if receipt["protocol"] == "legacy-plain":
            if sources or group["draft"] is not None or receipt["text_hash"] != receipt["result_hash"]:
                raise ValueError("Legacy output acquired typed metadata")
            if messages[key]["visibility"] == "visible" and checksum(messages[key]["body"]) != receipt["text_hash"]:
                raise ValueError("Legacy body changed")
            continue
        turn, thread = turns[key[:3]], threads[key[:2]]
        if ((turn["mode"] == "read") != bool(sources) or (turn["mode"] == "draft") != (group["draft"] is not None)
                or turn["draft_kind"] != "task"):
            raise ValueError("Incomplete result mode")
        if ([row["ordinal"] for row in sources] != list(range(1, len(sources) + 1)) or len(sources) > 2
                or len({(row["source_workspace_id"], row["receipt_id"]) for row in sources}) != len(sources)
                or sources and group["draft"] is not None):
            raise ValueError("Result source ordering or completeness changed")
        metadata = None
        if group["draft"] is not None:
            draft = group["draft"]
            metadata = CreateTask("task.create", _uuid(draft["draft_id"]), _uuid(thread["class_id"]), _uuid(thread["term_id"]), "digest projection").canonical()
            metadata.pop("title")
            metadata["title_hash"] = draft["title_hash"]
        canonical_sources = [{column: row[column] for column in ("source_id", "source_workspace_id", "source_owner_id", "receipt_id", "projection_hash", "as_of")} for row in sources]
        if checksum(result_canonical(receipt["text_hash"], canonical_sources, metadata)) != receipt["result_hash"]:
            raise ValueError("Result metadata changed after completion or clear")
        if messages[key]["visibility"] == "visible":
            # Body/type/budget check only; full digest verification is separate.
            ProducedResult(messages[key]["body"])
            if checksum(messages[key]["body"]) != receipt["text_hash"]:
                raise ValueError("Result body digest changed")
    return groups
