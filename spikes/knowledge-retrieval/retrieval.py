"""Synthetic-only retrieval experiment. No production gateway or persistence adapter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import re


def identifier(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("invalid synthetic identifier")


def aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timezone-aware time required")


@dataclass(frozen=True)
class Scope:
    workspace: str
    collection: str
    owner: str
    purpose: str

    def __post_init__(self) -> None:
        for value in (self.workspace, self.collection, self.owner, self.purpose):
            identifier(value)


@dataclass(frozen=True)
class Source:
    scope: Scope
    document: str
    version: int
    text: str
    valid_from: datetime
    valid_until: datetime
    supersedes: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Scope):
            raise ValueError("scope required")
        identifier(self.document)
        if type(self.version) is not int or self.version < 1:
            raise ValueError("positive integer version required")
        if self.supersedes is not None and (
            type(self.supersedes) is not int or self.supersedes != self.version - 1
        ):
            raise ValueError("supersession must reference the preceding version")
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > 64_000:
            raise ValueError("source must contain 1..64000 characters")
        if len(self.text.splitlines()) > 2000 or "\x00" in self.text:
            raise ValueError("invalid source lines")
        aware(self.valid_from)
        aware(self.valid_until)
        if self.valid_until <= self.valid_from:
            raise ValueError("invalid validity interval")

    @property
    def digest(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Citation:
    scope: Scope
    document: str
    version: int
    digest: str
    line: int


@dataclass(frozen=True)
class Evidence:
    citation: Citation
    excerpt: str


@dataclass(frozen=True)
class SearchResult:
    status: str
    evidence: tuple[Evidence, ...] = ()


class SyntheticSources:
    """Fake source authority for fixtures; this is deliberately not a business writer."""

    def __init__(self) -> None:
        self._current: dict[tuple[Scope, str], Source] = {}
        self._revoked: set[tuple[Scope, str, int]] = set()

    def publish(self, source: Source) -> None:
        key = source.scope, source.document
        previous = self._current.get(key)
        if previous == source:
            return
        expected = previous.version + 1 if previous else 1
        predecessor = previous.version if previous else None
        if source.version != expected or source.supersedes != predecessor:
            raise ValueError("versions are append-only; no substitution or rollback")
        self._current[key] = source

    def revoke(self, scope: Scope, document: str) -> None:
        current = self._current.get((scope, document))
        if current is None:
            raise ValueError("unknown synthetic source")
        self._revoked.add((scope, document, current.version))

    def available(self, scope: Scope, now: datetime) -> tuple[Source, ...]:
        aware(now)
        return tuple(sorted((source for (key_scope, _), source in self._current.items()
                            if key_scope == scope and self._active(source, now)),
                           key=lambda source: source.document))

    def _active(self, source: Source, now: datetime) -> bool:
        return (source.valid_from <= now < source.valid_until
                and (source.scope, source.document, source.version) not in self._revoked)

    def resolve(self, scope: Scope, citation: Citation, now: datetime) -> str | None:
        aware(now)
        if citation.scope != scope:
            return None
        current = self._current.get((scope, citation.document))
        if (current is None or not self._active(current, now)
                or type(citation.version) is not int or citation.version != current.version
                or citation.digest != current.digest
                or type(citation.line) is not int):
            return None
        lines = current.text.splitlines()
        if not 1 <= citation.line <= len(lines):
            return None
        return lines[citation.line - 1]


class SyntheticRetrieval:
    """One exact scope per index; caller-provided scope is NOT production authorization.

    Index entries contain references only. Every excerpt is read from current fake
    authority, and cached evidence must be validated again immediately before use.
    """

    def __init__(self, sources: SyntheticSources, scope: Scope) -> None:
        self._sources = sources
        self._scope = scope
        self._index: tuple[Citation, ...] = ()

    def rebuild(self, now: datetime) -> None:
        self._index = tuple(Citation(source.scope, source.document, source.version,
                                     source.digest, line)
                            for source in self._sources.available(self._scope, now)
                            for line, text in enumerate(source.text.splitlines(), 1)
                            if text.strip())

    def search(self, scope: Scope, query: str, now: datetime, limit: int = 5) -> SearchResult:
        aware(now)
        if scope != self._scope:
            return SearchResult("refused")
        if (not isinstance(query, str) or not query.strip() or len(query) > 256
                or type(limit) is not int or not 1 <= limit <= 20):
            raise ValueError("query/limit outside experiment bounds")
        terms = tuple(dict.fromkeys(re.findall(r"\w+", query.casefold())))
        if not terms:
            return SearchResult("no_answer")
        hits = []
        for citation in self._index:
            text = self._sources.resolve(scope, citation, now)
            if text is not None and all(term in text.casefold() for term in terms):
                hits.append(Evidence(citation, text))
                if len(hits) == limit:
                    break
        return SearchResult("evidence" if hits else "no_answer", tuple(hits[:limit]))

    def validate(self, scope: Scope, result: SearchResult, now: datetime) -> SearchResult:
        """Fail the whole cached evidence set if any source has changed or expired."""
        aware(now)
        if scope != self._scope:
            return SearchResult("refused")
        if result.status != "evidence" or not result.evidence:
            return SearchResult("no_answer")
        for item in result.evidence:
            current = self._sources.resolve(scope, item.citation, now)
            if current is None or current != item.excerpt:
                return SearchResult("stale")
        return result
