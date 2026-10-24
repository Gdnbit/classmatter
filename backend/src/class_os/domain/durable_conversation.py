"""Post-R1 interaction rules only; no persistence, authority, SDK loop or dispatch.

An authenticated BCG adapter must enforce these transitions atomically with CAS,
audit and scope checks. Constructing a value here is never a write authorization.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

import rfc8785

from .activity import content, instant, version
from .roster import identifiers


ACTIVE_STATES = frozenset({"queued", "running", "cancel_requested"})
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "interrupted", "unknown"})


@dataclass(frozen=True)
class ConversationScope:
    workspace_id: UUID
    owner_id: UUID
    class_id: UUID
    term_id: UUID
    student_id: UUID | None = None

    def __post_init__(self):
        identifiers(self.workspace_id, self.owner_id, self.class_id, self.term_id)
        if self.student_id is not None:
            identifiers(self.student_id)

    def canonical(self):
        return {key: str(value) if value is not None else None for key, value in vars(self).items()}


def visible_text(value):
    content(value, required=True, maximum=8000)
    if len(value.encode("utf-8")) > 16000:
        raise ValueError("Conversation text exceeds byte limit")


@dataclass(frozen=True)
class VisibleMessage:
    role: str
    origin: str
    text: str

    def __post_init__(self):
        if (self.role, self.origin) not in (("user", "user-original"), ("assistant", "assistant-unverified")):
            raise ValueError("Unsupported visible message origin")
        visible_text(self.text)


@dataclass(frozen=True)
class SendIntent:
    scope: ConversationScope
    thread_id: UUID
    client_request_id: UUID
    text: str
    mode: str
    draft_kind: str = "task"

    def __post_init__(self):
        if (type(self.scope) is not ConversationScope or self.mode not in ("read", "draft", "chat")
                or self.draft_kind not in ("task", "record-note")):
            raise ValueError("Unsupported conversation intent")
        identifiers(self.thread_id, self.client_request_id)
        visible_text(self.text)
        # Preserve the current Agent turn contract rather than accepting input
        # that would be durably saved but rejected by the existing runtime.
        content(self.text, required=True, maximum=2000)

    @property
    def request_hash(self):
        # Exact visible input: no strip/Unicode normalization that could hide a
        # changed request. Request key is a unique-key coordinate, not payload.
        return sha256(rfc8785.dumps({"schema": "classmatter.conversation-send.v1",
            "scope": self.scope.canonical(), "thread_id": str(self.thread_id),
            "text": self.text, "mode": self.mode, "draft_kind": self.draft_kind})).hexdigest()

    def is_replay_of(self, previous):
        if (type(previous) is not SendIntent or self.scope != previous.scope
                or self.thread_id != previous.thread_id or self.client_request_id != previous.client_request_id):
            return False
        if self.request_hash != previous.request_hash:
            raise ValueError("Conversation request key conflict")
        return True


@dataclass(frozen=True)
class ConversationRun:
    run_id: UUID
    state: str = "queued"
    version: int = 1
    generation: UUID | None = None
    started_at: datetime | None = None
    lease_until: datetime | None = None
    ended_at: datetime | None = None
    cancel_requested_at: datetime | None = None

    def __post_init__(self):
        identifiers(self.run_id)
        version(self.version)
        if self.state not in ACTIVE_STATES | TERMINAL_STATES:
            raise ValueError("Unsupported run state")
        if self.state == "queued":
            if any(value is not None for value in (self.generation, self.started_at, self.lease_until,
                                                   self.ended_at, self.cancel_requested_at)):
                raise ValueError("Queued run cannot have dispatch evidence")
            return
        if self.state in TERMINAL_STATES:
            instant(self.ended_at)
            if self.started_at is None:
                if (self.state != "cancelled" or self.generation is not None or self.lease_until is not None
                        or self.cancel_requested_at is not None):
                    raise ValueError("Only queued cancellation may precede dispatch")
                return
        elif self.ended_at is not None:
            raise ValueError("Active run cannot have terminal time")
        identifiers(self.generation)
        start, lease = instant(self.started_at), instant(self.lease_until)
        if not timedelta(0) < lease - start <= timedelta(minutes=5):
            raise ValueError("Invalid bounded run lease")
        if self.state == "cancel_requested" and self.cancel_requested_at is None:
            raise ValueError("Cancellation request time required")
        if self.cancel_requested_at is not None:
            requested = instant(self.cancel_requested_at)
            if (not start <= requested < lease or self.state in ("running", "completed")
                    or (self.ended_at is not None and instant(self.ended_at) < requested)):
                raise ValueError("Invalid cancellation chronology")
        if self.ended_at is not None:
            end = instant(self.ended_at)
            if end < start or (end < lease if self.state == "interrupted" else end >= lease):
                raise ValueError("Invalid terminal lease chronology")

    def _cas(self, expected_version):
        version(expected_version)
        if expected_version != self.version:
            raise ValueError("Stale conversation run version")

    def start(self, expected_version, generation, now, lease_until):
        self._cas(expected_version)
        if self.state != "queued":
            raise ValueError("Run cannot be dispatched again")
        return replace(self, state="running", version=self.version + 1, generation=generation,
                       started_at=instant(now), lease_until=instant(lease_until))

    def request_cancel(self, expected_version, now):
        self._cas(expected_version)
        at = instant(now)
        if self.state == "queued":
            return replace(self, state="cancelled", version=self.version + 1, ended_at=at)
        if self.state not in ("running", "cancel_requested"):
            raise ValueError("Run already terminal")
        if (at < instant(self.started_at) or at >= instant(self.lease_until)
                or (self.cancel_requested_at is not None and at < instant(self.cancel_requested_at))):
            raise ValueError("Run requires expiry reconciliation")
        if self.state == "cancel_requested":
            return self
        return replace(self, state="cancel_requested", version=self.version + 1, cancel_requested_at=at)

    def finish(self, expected_version, generation, state, now):
        self._cas(expected_version)
        at = instant(now)
        if (self.state not in ("running", "cancel_requested") or generation != self.generation
                or type(generation) is not UUID or at < instant(self.started_at) or at >= instant(self.lease_until)
                or state not in ("completed", "failed", "cancelled", "unknown")
                or (self.state == "cancel_requested" and state == "completed")):
            raise ValueError("Invalid or fenced run completion")
        return replace(self, state=state, version=self.version + 1, ended_at=at)

    def expire(self, expected_version, now):
        self._cas(expected_version)
        at = instant(now)
        if self.state not in ("running", "cancel_requested") or at < instant(self.lease_until):
            raise ValueError("Run lease has not expired")
        # Interrupted says this application stopped accepting the old worker;
        # it does not prove supplier cancellation, absence of charges or retry.
        return replace(self, state="interrupted", version=self.version + 1, ended_at=at)
