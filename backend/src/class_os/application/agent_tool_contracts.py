"""Closed versioned metadata for existing R1 tools; never a dynamic registry.

The SDK still derives/validates/calls functions. This catalog cannot authorize
a read/write, register a callable, or replace the QG/BCG/ISB.
"""
from copy import deepcopy

from .agent import Mode, DraftKind


_CONTRACTS = (
    {
        "schema_version": "class-os.tool-contract.v1", "version": 1,
        "name": "attention_list", "mode": "read",
        "kind": "function", "strict": None,
        "description": "Read fresh authorized class work; no student narratives or sensitive record text.",
        "parameters_json_schema": {"additionalProperties": False, "properties": {}, "type": "object"},
        "purpose": "Read current class or explicitly selected student work counts with a durable query receipt.",
        "required_boundary": "query-gateway",
        "reads": ["current-authorized-work-projection"],
        "steps": ["revalidate-bound-scope", "query-and-audit", "return-fixed-counts-and-source-receipt"],
        "output": "WorkSnapshot.tool_payload; internal identity and record text excluded.",
        "side_effect": "no-business-write",
        "confirmation": "none-for-read; scope is teacher-selected, never model-selected",
        "forbidden": ["repository-access", "scope-retarget", "approval", "business-write", "sql", "ddl"],
        "failure": "fail-run-without-answer-draft-or-new-history; no-class-fallback-or-automatic-retry",
        "idempotency": "fresh-authorized-read-not-replay-of-history; durable-read-audit-is-appended",
    },
    {
        "schema_version": "class-os.tool-contract.v1", "version": 1,
        "name": "task_draft", "mode": "draft",
        "kind": "function", "strict": None,
        "description": "Build an ephemeral editable task draft. Never saves, approves, or commits.",
        "parameters_json_schema": {"additionalProperties": False, "properties": {"title": {"type": "string"}},
                                   "required": ["title"], "type": "object"},
        "purpose": "Build one ephemeral task candidate for an existing trusted UI form, not a fact or assignment.",
        "required_boundary": "authorized-ephemeral-agent-context",
        "reads": [],
        "steps": ["validate-title-with-owning-domain", "build-one-in-memory-candidate", "handoff-to-trusted-ui"],
        "output": "Uncommitted status/title to SDK; fixed CreateTask candidate to UI. Domain name rule limits title to 80 characters.",
        "side_effect": "ephemeral-candidate-only",
        "confirmation": "trusted-UI-review-preview-and-required-approval-before-BCG-commit; no-Agent-approval",
        "forbidden": ["repository-access", "saved-fact", "accepted-handoff", "approval", "business-write", "sql", "ddl"],
        "failure": "fail-run-without-answer-draft-or-new-history; no-automatic-retry-or-commit",
        "idempotency": "one-candidate-per-run; not-a-durable-command-or-replayable-receipt",
    },
    {
        "schema_version": "class-os.tool-contract.v1", "version": 1,
        "name": "record_note_draft", "mode": "record-note-draft", "kind": "function", "strict": None,
        "description": "Quote this user's current message verbatim into one unverified note candidate. Never chooses a student, time or fact type, saves, approves, or commits.",
        "parameters_json_schema": {"additionalProperties": False, "properties": {"note_quote": {"type": "string"}},
                                   "required": ["note_quote"], "type": "object"},
        "purpose": "Excerpt current user-authored notes for manual Record review, never invent or verify a fact.",
        "required_boundary": "authorized-ephemeral-agent-context",
        "reads": ["current-user-message-verbatim-only"],
        "steps": ["verify-verbatim-current-message-span", "bind-code-point-span-and-sha256", "handoff-to-trusted-record-form"],
        "output": "Unverified note quote/span/hash candidate, without student, event time, type, record ID or command. Quote is limited to 1000 code points.",
        "side_effect": "ephemeral-candidate-only",
        "confirmation": "teacher-selects-student-type-time-and-reviews-edits-text-before-original-BCG-preview-and-confirmation",
        "forbidden": ["invention", "history-as-source", "identity-resolution", "inferred-event-time", "saved-fact", "approval", "business-write", "sql", "ddl"],
        "failure": "fail-run-without-answer-draft-or-new-history; no-automatic-retry-or-commit",
        "idempotency": "one-candidate-per-run; no-durable-command-or-verified-fact",
    },
)


def catalog():
    return deepcopy(_CONTRACTS)


def for_mode(mode, draft_kind=DraftKind.TASK):
    if type(mode) is not Mode or type(draft_kind) is not DraftKind or (mode is not Mode.DRAFT and draft_kind is not DraftKind.TASK):
        raise ValueError("Explicit registered Agent mode required")
    profile = "record-note-draft" if draft_kind is DraftKind.RECORD_NOTE else mode.value
    return tuple(item for item in catalog() if item["mode"] == profile)
