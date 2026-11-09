"""Workspace-owned interaction values; candidates never authorize business writes."""
from datetime import timedelta
from hashlib import sha256
from uuid import UUID

import rfc8785

from .activity import instant, content
from .roster import identifiers, decode
from .documents import decode_document
from .classroom_work import COMMANDS as CLASSROOM_COMMANDS, decode_classroom


PROFILE = "workspace-chat-d3"
ACTIVE = frozenset({"queued", "running"})
TERMINAL = frozenset({"completed", "failed", "cancelled", "unknown"})
CANDIDATES = frozenset({"class.create", "class.update", "term.update", "student.create", "student.update_name",
                        "task.create", "task.update", "document.create", "document.revise", *CLASSROOM_COMMANDS})
MAX_TURNS = 10_000
LEASE = timedelta(minutes=5)


def message(value, *, assistant=False):
    content(value, required=True, maximum=4000 if assistant else 2000)
    if len(value.encode("utf-8")) > (16000 if assistant else 8000):
        raise ValueError("Chat message exceeds byte limit")
    return value


def input_hash(workspace_id, owner_id, thread_id, text):
    identifiers(workspace_id, owner_id, thread_id)
    message(text)
    return sha256(rfc8785.dumps({"schema": "classmatter.workspace-chat-input.v1", "workspace_id": str(workspace_id),
        "owner_id": str(owner_id), "thread_id": str(thread_id), "text": text})).hexdigest()


def candidate(payload):
    if type(payload) is not dict or payload.get("command") not in CANDIDATES:
        raise ValueError("Unsupported conversational candidate")
    command = (decode_classroom(payload) if payload['command'] in CLASSROOM_COMMANDS
               else decode_document(payload) if payload["command"].startswith("document.") else decode(payload))
    if command.canonical() != payload or len(rfc8785.dumps(payload)) > 440_000:
        raise ValueError("Noncanonical conversational candidate")
    return command


def candidate_hash(payload):
    candidate(payload)
    return sha256(rfc8785.dumps(payload)).hexdigest()


def validate_turn(row, *, cleared=False):
    for key in ("workspace_id", "thread_id", "turn_id", "request_id"):
        identifiers(row[key])
    if type(row["ordinal"]) is not int or not 1 <= row["ordinal"] <= MAX_TURNS:
        raise ValueError("Invalid turn ordinal")
    if row["state"] not in ACTIVE | TERMINAL or type(row["version"]) is not int or row["version"] < 1:
        raise ValueError("Invalid turn state")
    start = instant(row["created_at"])
    if any(row[key] is not None and (type(row[key]) is not int or not 0 <= row[key] <= 2147483647)
           for key in ("input_tokens", "output_tokens", "duration_ms")):
        raise ValueError("Invalid run measurements")
    if row["state"] == "queued":
        if any(row[key] is not None for key in ("generation", "started_at", "lease_until", "ended_at")):
            raise ValueError("Queued turn cannot contain run evidence")
    else:
        if row["started_at"] is not None:
            identifiers(row["generation"])
            if not start <= instant(row["started_at"]) < instant(row["lease_until"]) <= instant(row["started_at"]) + LEASE:
                raise ValueError("Invalid run lease")
        elif row["state"] != "cancelled" or any(row[key] is not None for key in ("generation", "lease_until")):
            raise ValueError("Only queued cancellation can precede a claim")
        if row["state"] in TERMINAL:
            if instant(row["ended_at"]) < (row["started_at"] or start):
                raise ValueError("Invalid completion time")
            if row["state"] == "completed" and instant(row["ended_at"]) >= instant(row["lease_until"]):
                raise ValueError("Completion after run lease")
        elif row["ended_at"] is not None:
            raise ValueError("Active run has completion time")
    if cleared:
        if any(row[key] is not None for key in ("user_text", "assistant_text", "candidate", "candidate_hash")):
            raise ValueError("Cleared turn retained visible content")
    else:
        message(row["user_text"])
        if row["state"] == "completed":
            message(row["assistant_text"], assistant=True)
        elif row["assistant_text"] is not None or row["candidate"] is not None:
            raise ValueError("Incomplete run released an answer or candidate")
        if (row["candidate"] is None) != (row["candidate_hash"] is None):
            raise ValueError("Incomplete candidate hash")
        if row["candidate"] is not None and candidate_hash(row["candidate"]) != row["candidate_hash"]:
            raise ValueError("Candidate hash mismatch")
    return row
