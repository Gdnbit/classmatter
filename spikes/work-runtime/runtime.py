"""Isolated synthetic work recovery. No production tools, storage or authorization."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
import json
import re
from threading import RLock


def instant(value: datetime) -> None:
    if type(value) is not datetime or value.utcoffset() != timedelta(0):
        raise ValueError("aware UTC time required")


def identifier(value: str) -> None:
    if type(value) is not str or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("synthetic identifier required")


def digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Scope:
    workspace: str
    owner: str
    purpose: str

    def __post_init__(self):
        for value in (self.workspace, self.owner, self.purpose):
            identifier(value)


@dataclass(frozen=True)
class Request:
    scope: Scope
    key: str
    source: str
    revision: int
    value: str
    deadline: datetime
    tool: str = "fake.review.v1"

    def __post_init__(self):
        if type(self.scope) is not Scope:
            raise ValueError("synthetic scope required")
        identifier(self.key)
        identifier(self.source)
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("positive source revision required")
        if type(self.value) is not str or not self.value.strip() or len(self.value) > 2000:
            raise ValueError("bounded synthetic value required")
        if type(self.tool) is not str or self.tool != "fake.review.v1":
            raise ValueError("only the fixed fake tool is registered")
        instant(self.deadline)

    @property
    def operation(self) -> str:
        return digest([self.scope.workspace, self.scope.owner, self.scope.purpose, self.key])

    @property
    def fingerprint(self) -> str:
        return digest([self.operation, self.source, self.revision, self.value,
                       self.deadline.isoformat(), self.tool])


@dataclass(frozen=True)
class Approval:
    generation: int
    expires: datetime
    revoked: bool = False


class FakeAuthority:
    """Fixture-only source and fake human approval service; never an ISB/BCG port."""

    def __init__(self):
        self.scopes: set[Scope] = set()
        self.sources: dict[tuple[Scope, str], tuple[int, bool]] = {}
        self.approvals: dict[str, Approval] = {}

    def source(self, scope: Scope, source: str, revision: int, *, active=True):
        if type(scope) is not Scope:
            raise ValueError("synthetic scope required")
        identifier(source)
        if type(revision) is not int or revision < 1 or type(active) is not bool:
            raise ValueError("invalid source revision")
        previous = self.sources.get((scope, source))
        if previous is not None and revision <= previous[0]:
            raise ValueError("source changes require a newer revision")
        self.sources[scope, source] = revision, active

    def approve(self, request: Request, now: datetime, until: datetime):
        instant(now)
        instant(until)
        if (request.scope not in self.scopes
                or self.sources.get((request.scope, request.source)) != (request.revision, True)
                or not now < until <= request.deadline):
            raise ValueError("fake approval scope/source/expiry mismatch")
        previous = self.approvals.get(request.fingerprint)
        self.approvals[request.fingerprint] = Approval(previous.generation + 1 if previous else 1, until)

    def revoke(self, request: Request):
        approval = self.approvals.get(request.fingerprint)
        if approval is None:
            raise ValueError("no fake approval to revoke")
        self.approvals[request.fingerprint] = replace(approval, revoked=True)

    def check(self, request: Request, now: datetime) -> tuple[str | None, int | None]:
        instant(now)
        if now >= request.deadline:
            return "deadline", None
        if request.scope not in self.scopes:
            return "scope_revoked", None
        if self.sources.get((request.scope, request.source)) != (request.revision, True):
            return "source_changed", None
        approval = self.approvals.get(request.fingerprint)
        if approval is None:
            return "approval_required", None
        if approval.revoked:
            return "approval_revoked", None
        if now >= approval.expires:
            return "approval_expired", None
        return None, approval.generation


class Unavailable(RuntimeError):
    pass


class BeforeEffect(RuntimeError):
    pass


class LostReceipt(RuntimeError):
    pass


class SimulatedCrash(RuntimeError):
    pass


@dataclass(frozen=True)
class Receipt:
    operation: str
    request_hash: str
    result_hash: str
    tool: str = "fake.review.v1"


class FakeTool:
    """Only effect: record a deterministic synthetic review receipt in memory."""

    def __init__(self):
        self._receipts: dict[str, Receipt] = {}
        self._lock = RLock()
        self.calls = 0
        self.effects = 0
        self.fail_before = 0
        self.lose_receipt = False
        self.lookup_unavailable = False

    @staticmethod
    def expected(request: Request) -> Receipt:
        return Receipt(request.operation, request.fingerprint, digest(["synthetic-reviewed", request.value]))

    def lookup(self, request: Request) -> Receipt | None:
        with self._lock:
            if self.lookup_unavailable:
                raise Unavailable("fake receipt lookup unavailable")
            receipt = self._receipts.get(request.operation)
            if receipt is not None and receipt != self.expected(request):
                raise ValueError("fake receipt integrity mismatch")
            return receipt  # None is authoritative no-effect proof in THIS fake only.

    def execute(self, request: Request) -> Receipt:
        with self._lock:
            self.calls += 1
            prior = self.lookup(request)
            if prior is not None:
                return prior
            if self.fail_before:
                self.fail_before -= 1
                raise BeforeEffect("fixture failure before any effect")
            receipt = self.expected(request)
            self._receipts[request.operation] = receipt
            self.effects += 1
            if self.lose_receipt:
                self.lose_receipt = False
                raise LostReceipt("effect recorded, reply lost")
            return receipt


@dataclass(frozen=True)
class Work:
    request: Request
    state: str = "approval_wait"
    attempts: int = 0
    generation: int = 0
    approval_generation: int | None = None
    lease_until: datetime | None = None
    next_at: datetime | None = None
    dispatched: bool = False
    receipt: Receipt | None = None
    reason: str | None = None
    recovery_checks: int = 0


@dataclass(frozen=True)
class Ticket:
    operation: str
    generation: int


@dataclass(frozen=True)
class Event:
    operation: str
    state: str
    attempts: int
    reason: str | None
    at: datetime


class FakeStore:
    """Survives simulated worker replacement, NOT actual process/host loss."""

    def __init__(self):
        self.lock = RLock()
        self._rows: dict[str, Work] = {}
        self.events: list[Event] = []
        self.fail_next_write = False
        self.policy: tuple[int, int, int] | None = None

    def get(self, operation: str) -> Work:
        with self.lock:
            return self._rows[operation]

    def put(self, work: Work, now: datetime):
        if self._rows.get(work.request.operation) == work:
            return
        if self.fail_next_write:
            self.fail_next_write = False
            raise Unavailable("fake atomic state/event write failed")
        self._rows[work.request.operation] = work
        self.events.append(Event(work.request.operation, work.state, work.attempts, work.reason, now))


TERMINAL = frozenset({"completed", "cancelled", "blocked", "exhausted"})


class Runtime:
    def __init__(self, store: FakeStore, authority: FakeAuthority, tool: FakeTool,
                 *, max_attempts=3, lease_seconds=10, backoff_seconds=2):
        if type(store) is not FakeStore or type(authority) is not FakeAuthority or type(tool) is not FakeTool:
            raise ValueError("only fixed fixture components are allowed")
        for value in (max_attempts, lease_seconds, backoff_seconds):
            if type(value) is not int or not 1 <= value <= 60:
                raise ValueError("bounded positive runtime policy required")
        self.store, self.authority, self.tool = store, authority, tool
        self.max_attempts, self.lease_seconds, self.backoff_seconds = max_attempts, lease_seconds, backoff_seconds
        with store.lock:
            policy = max_attempts, lease_seconds, backoff_seconds
            if store.policy is not None and store.policy != policy:
                raise ValueError("worker replacement cannot change the fixture store policy")
            store.policy = policy

    def enqueue(self, request: Request, now: datetime) -> Work:
        instant(now)
        with self.store.lock:
            prior = self.store._rows.get(request.operation)
            if prior is not None:
                if prior.request != request:
                    raise ValueError("idempotency key reused with different input")
                return prior
            work = Work(request)
            self.store.put(work, now)
            return work

    def _authorized(self, work: Work, now: datetime, *, same_approval=False) -> bool:
        reason, generation = self.authority.check(work.request, now)
        if reason is None and same_approval and generation != work.approval_generation:
            reason = "approval_changed"
        if reason is not None:
            state = "approval_wait" if reason == "approval_required" and not same_approval else "blocked"
            self.store.put(replace(work, state=state, reason=reason), now)
            return False
        return True

    def claim(self, operation: str, now: datetime) -> Ticket | None:
        instant(now)
        with self.store.lock:
            work = self.store.get(operation)
            if work.state not in ("approval_wait", "retry_wait"):
                return None
            if work.next_at is not None and now < work.next_at:
                return None
            if not self._authorized(work, now):
                return None
            if work.attempts >= self.max_attempts:
                self.store.put(replace(work, state="exhausted", reason="attempt_limit"), now)
                return None
            _, approval = self.authority.check(work.request, now)
            work = replace(work, state="running", attempts=work.attempts + 1,
                           generation=work.generation + 1, approval_generation=approval,
                           lease_until=min(now + timedelta(seconds=self.lease_seconds), work.request.deadline),
                           next_at=None, dispatched=False, reason=None)
            self.store.put(work, now)
            return Ticket(operation, work.generation)

    def _live(self, ticket: Ticket, now: datetime) -> Work | None:
        work = self.store.get(ticket.operation)
        if (work.state != "running" or type(ticket.generation) is not int
                or ticket.generation != work.generation or now >= work.lease_until):
            return None
        return work if self._authorized(work, now, same_approval=True) else None

    def dispatch(self, ticket: Ticket, now: datetime, *, crash: str | None = None):
        instant(now)
        if crash not in (None, "before_effect", "after_effect"):
            raise ValueError("unknown crash fixture")
        with self.store.lock:
            work = self._live(ticket, now)
            if work is None or work.dispatched:
                return None
            self.store.put(replace(work, dispatched=True), now)
            # Lock serializes fixture dispatch with cancellation/revocation tests.
            if crash == "before_effect":
                raise SimulatedCrash("worker lost after dispatch intent, before fake tool")
            try:
                receipt = self.tool.execute(work.request)
            except BeforeEffect:
                self._retry(self.store.get(ticket.operation), now)
                return None
            except (LostReceipt, Unavailable):
                self.store.put(replace(self.store.get(ticket.operation), state="unknown", reason="receipt_unknown"), now)
                return None
            except ValueError:
                self.store.put(replace(self.store.get(ticket.operation), state="blocked", reason="receipt_mismatch"), now)
                return None
            if crash == "after_effect":
                raise SimulatedCrash("worker lost after fake effect, before outcome commit")
            return receipt

    def finish(self, ticket: Ticket, receipt: Receipt, now: datetime) -> bool:
        instant(now)
        with self.store.lock:
            work = self._live(ticket, now)
            if work is None or not work.dispatched:
                return False
            try:
                actual = self.tool.lookup(work.request)
            except (Unavailable, ValueError):
                return False
            if actual is None or type(receipt) is not Receipt or actual != receipt:
                return False
            self.store.put(replace(work, state="completed", receipt=actual, reason=None), now)
            return True

    def _retry(self, work: Work, now: datetime):
        if work.attempts >= self.max_attempts:
            self.store.put(replace(work, state="exhausted", reason="attempt_limit"), now)
        else:
            delay = min(60, self.backoff_seconds * 2 ** (work.attempts - 1))
            self.store.put(replace(work, state="retry_wait", next_at=now + timedelta(seconds=delay),
                                   reason="verified_no_effect"), now)

    def recover(self, operation: str, now: datetime) -> Work:
        instant(now)
        with self.store.lock:
            work = self.store.get(operation)
            if work.state not in ("running", "unknown") or now < work.lease_until:
                return work
            if work.next_at is not None and now < work.next_at:
                return work
            if not self._authorized(work, now, same_approval=True):
                return self.store.get(operation)
            work = replace(work, recovery_checks=work.recovery_checks + 1)
            try:
                actual = self.tool.lookup(work.request)
            except Unavailable:
                stopped = work.recovery_checks >= self.max_attempts
                self.store.put(replace(work, state="blocked" if stopped else "unknown",
                                       next_at=now + timedelta(seconds=60),
                                       reason="reconciliation_limit" if stopped else "lookup_unavailable"), now)
            except ValueError:
                self.store.put(replace(work, state="blocked", reason="receipt_mismatch"), now)
            else:
                if actual is not None:
                    if not work.dispatched:
                        self.store.put(replace(work, state="blocked", reason="unexpected_receipt"), now)
                    else:
                        self.store.put(replace(work, state="completed", receipt=actual, reason="verified_recovery"), now)
                else:
                    self._retry(work, now)
            return self.store.get(operation)

    def cancel(self, operation: str, now: datetime) -> Work:
        instant(now)
        with self.store.lock:
            work = self.store.get(operation)
            if work.state not in TERMINAL:
                self.store.put(replace(work, state="cancelled", reason="human_cancelled"), now)
            return self.store.get(operation)
