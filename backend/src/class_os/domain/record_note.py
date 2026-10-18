"""Unverified excerpt of this user message, never a stored fact or inference."""
from dataclasses import dataclass
import hashlib
import re

from .activity import content


@dataclass(frozen=True)
class RecordNoteCandidate:
    note_quote: str
    source_start: int
    source_end: int
    source_hash: str

    def __post_init__(self):
        content(self.note_quote, required=True, maximum=1000)
        if (type(self.source_start) is not int or type(self.source_end) is not int
                or not 0 <= self.source_start < self.source_end <= 2000
                or self.source_end - self.source_start != len(self.note_quote)
                or type(self.source_hash) is not str or not re.fullmatch(r"[a-f0-9]{64}", self.source_hash)):
            raise ValueError("Invalid unverified note source")

    @classmethod
    def from_message(cls, message, note_quote):
        content(message, required=True, maximum=2000)
        content(note_quote, required=True, maximum=1000)
        start = message.find(note_quote)
        if start < 0:
            raise ValueError("Note must quote the current user message verbatim")
        return cls(note_quote, start, start + len(note_quote), hashlib.sha256(message.encode("utf-8")).hexdigest())

    def canonical(self):
        return {"schema_version": "class-os.record-note-candidate.v1", "status": "unverified-user-note",
                "note_quote": self.note_quote, "source_start": self.source_start,
                "source_end": self.source_end, "source_hash": self.source_hash}
