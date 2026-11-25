"""Synthetic text/file capture with source-bound drafts and explicit human review."""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from datetime import datetime, timedelta
from hashlib import sha256
import json
import re
import unicodedata


def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise ValueError("synthetic stable identifier required")


def instant(value):
    if type(value) is not datetime or value.utcoffset() != timedelta(0):
        raise ValueError("aware UTC time required")


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Scope:
    workspace: str
    classroom: str
    term: str
    owner: str
    purpose: str = "capture"

    def __post_init__(self):
        for value in asdict(self).values():
            identifier(value)


@dataclass(frozen=True)
class Source:
    scope: Scope
    source_id: str
    version: int
    text: str
    valid_until: datetime
    active: bool = True

    def __post_init__(self):
        if type(self.scope) is not Scope or type(self.version) is not int or self.version < 1:
            raise ValueError("typed source scope/version required")
        identifier(self.source_id)
        instant(self.valid_until)
        if (type(self.text) is not str or not self.text.strip() or len(self.text) > 64_000
                or len(self.text.splitlines()) > 500 or "\x00" in self.text or type(self.active) is not bool):
            raise ValueError("source outside text/line bounds")

    @property
    def digest(self):
        return sha256(self.text.encode("utf-8")).hexdigest()


class SyntheticSources:
    def __init__(self):
        self._sources: dict[tuple[Scope, str], Source] = {}

    def publish(self, source: Source):
        if type(source) is not Source:
            raise ValueError("typed synthetic source required")
        key = source.scope, source.source_id
        previous = self._sources.get(key)
        if previous == source:
            return
        if source.version != (previous.version + 1 if previous else 1) or not source.active:
            raise ValueError("source revisions must be append-only and active on publication")
        self._sources[key] = source

    def withdraw(self, scope: Scope, source_id: str):
        key = scope, source_id
        if key not in self._sources:
            raise ValueError("missing source")
        self._sources[key] = replace(self._sources[key], active=False)

    def read(self, scope: Scope, source_id: str, now: datetime):
        instant(now)
        source = self._sources.get((scope, source_id))
        if source is None or not source.active or now >= source.valid_until:
            raise ValueError("source missing, withdrawn or expired")
        return source


@dataclass(frozen=True)
class Person:
    student_id: str
    name: str

    def __post_init__(self):
        identifier(self.student_id)
        if type(self.name) is not str or not self.name.strip() or len(self.name) > 80 or any(ord(char) < 32 for char in self.name):
            raise ValueError("bounded synthetic display name required")


@dataclass(frozen=True)
class Roster:
    scope: Scope
    version: int
    people: tuple[Person, ...]

    def __post_init__(self):
        if type(self.scope) is not Scope or type(self.version) is not int or self.version < 1:
            raise ValueError("typed roster scope/version required")
        if (type(self.people) is not tuple or len(self.people) > 2000 or any(type(person) is not Person for person in self.people)
                or len({person.student_id for person in self.people}) != len(self.people)):
            raise ValueError("bounded roster with unique IDs required")

    @property
    def digest(self):
        return fingerprint([self.version, asdict(self.scope), sorted((person.student_id, person.name) for person in self.people)])


@dataclass(frozen=True)
class SourceRef:
    scope: Scope
    source_id: str
    version: int
    digest: str
    line: int
    start: int
    end: int

    def __post_init__(self):
        if type(self.scope) is not Scope:
            raise ValueError("typed source scope required")
        identifier(self.source_id)
        if (any(type(value) is not int for value in (self.version, self.line, self.start, self.end))
                or self.version < 1 or self.line < 1 or not 0 <= self.start < self.end <= 64_000
                or type(self.digest) is not str or not re.fullmatch(r"[a-f0-9]{64}", self.digest)):
            raise ValueError("invalid source locator")


@dataclass(frozen=True)
class Draft:
    draft_id: str
    source: SourceRef
    roster_version: int
    roster_digest: str
    mention: str
    kind: str
    text: str
    quote: str
    candidate_ids: tuple[str, ...]
    state: str

    def __post_init__(self):
        if (type(self.source) is not SourceRef or type(self.roster_version) is not int or self.roster_version < 1
                or type(self.kind) is not str or self.kind not in ("note", "task")
                or any(type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value)
                       for value in (self.draft_id, self.roster_digest))):
            raise ValueError("invalid draft metadata")
        if (type(self.text) is not str or not self.text or len(self.text) > (80 if self.kind == "task" else 1000)
                or type(self.mention) is not str or not 1 <= len(self.mention) <= 80
                or type(self.quote) is not str or len(self.quote) != self.source.end - self.source.start):
            raise ValueError("invalid draft content/span")
        if type(self.candidate_ids) is not tuple or len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("unique candidate tuple required")
        for candidate in self.candidate_ids:
            identifier(candidate)
        expected = "unmatched" if not self.candidate_ids else "ambiguous" if len(self.candidate_ids) > 1 else "needs_review"
        if self.state != expected:
            raise ValueError("draft resolution state mismatch")


@dataclass(frozen=True)
class ParseIssue:
    source: SourceRef
    reason: str


@dataclass(frozen=True)
class CapturePreview:
    drafts: tuple[Draft, ...]
    issues: tuple[ParseIssue, ...]
    mode: str = "synthetic_drafts_only"


@dataclass(frozen=True)
class ReviewedCandidate:
    candidate_id: str
    draft: Draft
    student_id: str
    reviewer: str
    reviewed_at: datetime
    state: str = "reviewed_candidate_not_committed"


@dataclass(frozen=True)
class Review:
    draft_id: str
    decision: str
    candidate: ReviewedCandidate | None = None


class Capture:
    def __init__(self, sources: SyntheticSources, roster: Roster):
        if type(sources) is not SyntheticSources or type(roster) is not Roster:
            raise ValueError("fixed synthetic source/roster fixtures required")
        self.sources, self.roster = sources, roster
        self._reviewed: dict[str, ReviewedCandidate] = {}

    def replace_roster(self, roster: Roster):
        if type(roster) is not Roster or roster.scope != self.roster.scope or roster.version != self.roster.version + 1:
            raise ValueError("same-scope next roster version required")
        self.roster = roster

    def preview(self, scope: Scope, source_id: str, now: datetime) -> CapturePreview:
        if scope != self.roster.scope:
            raise ValueError("capture scope refused")
        source = self.sources.read(scope, source_id, now)
        offset, drafts, issues = 0, [], []
        for line_number, raw_line in enumerate(source.text.splitlines(keepends=True), 1):
            quote = raw_line.rstrip("\r\n")
            start = offset
            offset += len(raw_line)
            if not quote.strip():
                continue
            reference = SourceRef(scope, source_id, source.version, source.digest, line_number, start, start + len(quote))
            parts = [part.strip() for part in quote.split("|", 2)]
            if len(parts) != 3 or not parts[0] or parts[1] not in ("note", "task") or not parts[2]:
                issues.append(ParseIssue(reference, "use mention | note-or-task | literal text"))
                continue
            mention, kind, text = parts
            if len(mention) > 80 or len(text) > (80 if kind == "task" else 1000):
                issues.append(ParseIssue(reference, "field exceeds candidate bounds"))
                continue
            token = unicodedata.normalize("NFC", mention)
            if token.startswith("id:"):
                matches = [person.student_id for person in self.roster.people if person.student_id == token[3:]]
            elif token.startswith("name:"):
                matches = [person.student_id for person in self.roster.people if unicodedata.normalize("NFC", person.name) == token[5:]]
            else:
                matches = [person.student_id for person in self.roster.people
                           if person.student_id == token or unicodedata.normalize("NFC", person.name) == token]
            matches = tuple(sorted(set(matches)))
            state = "unmatched" if not matches else "ambiguous" if len(matches) > 1 else "needs_review"
            payload = [asdict(reference), self.roster.version, self.roster.digest, mention, kind, text, quote, matches, state]
            drafts.append(Draft(fingerprint(payload), reference, self.roster.version, self.roster.digest,
                                mention, kind, text, quote, matches, state))
            if len(drafts) > 100:
                raise ValueError("more than100 drafts; split the synthetic source")
        return CapturePreview(tuple(drafts), tuple(issues))

    def status(self, scope: Scope, draft: Draft, now: datetime) -> str:
        instant(now)
        if type(draft) is not Draft or type(draft.source) is not SourceRef or scope != self.roster.scope or draft.source.scope != scope:
            return "refused"
        try:
            source = self.sources.read(scope, draft.source.source_id, now)
        except ValueError:
            return "stale"
        if (source.version != draft.source.version or source.digest != draft.source.digest
                or draft.roster_version != self.roster.version or draft.roster_digest != self.roster.digest):
            return "stale"
        rebuilt = self.preview(scope, source.source_id, now)
        return "current" if draft in rebuilt.drafts else "invalid"

    def review(self, scope: Scope, draft: Draft, *, decision: str, selected: str | None,
               reviewer: str, now: datetime) -> Review:
        identifier(reviewer)
        if self.status(scope, draft, now) != "current":
            raise ValueError("draft/source/roster no longer current; recapture before review")
        if decision == "reject":
            if selected is not None:
                raise ValueError("rejection cannot select a student")
            return Review(draft.draft_id, "rejected")
        if decision != "accept" or selected not in draft.candidate_ids:
            raise ValueError("explicit human selection from current candidates required")
        candidate_id = fingerprint([draft.draft_id, selected, reviewer, now.isoformat()])
        candidate = ReviewedCandidate(candidate_id, draft, selected, reviewer, now)
        self._reviewed[candidate_id] = candidate
        return Review(draft.draft_id, "accepted_as_candidate_only", candidate)

    def candidate(self, scope: Scope, candidate_id: str, now: datetime) -> ReviewedCandidate | None:
        instant(now)
        candidate = self._reviewed.get(candidate_id)
        if candidate is None or self.status(scope, candidate.draft, now) != "current":
            return None
        return candidate
