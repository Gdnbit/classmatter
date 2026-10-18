"""Ephemeral read projection/proof, not a stored fact or attention score."""
from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID


@dataclass(frozen=True)
class WorkSnapshot:
    class_id: UUID
    term_id: UUID
    class_version: int
    as_of: datetime
    open_tasks: int
    waiting_tasks: int
    record_count: int
    source_hash: str
    audit_id: UUID | None = None
    student_id: UUID | None = None
    student_version: int | None = None

    def __post_init__(self):
        if (type(self.class_id) is not UUID or type(self.term_id) is not UUID
                or not isinstance(self.as_of, datetime) or self.as_of.utcoffset() is None
                or any(type(value) is not int or value < 0 for value in (self.open_tasks, self.waiting_tasks, self.record_count))
                or type(self.class_version) is not int or self.class_version < 1
                or self.waiting_tasks > self.open_tasks
                or not re.fullmatch(r"[a-f0-9]{64}", self.source_hash)
                or (self.audit_id is not None and type(self.audit_id) is not UUID)
                or ((self.student_id is None) != (self.student_version is None))
                or (self.student_id is not None and (type(self.student_id) is not UUID
                    or type(self.student_version) is not int or self.student_version < 1))):
            raise ValueError("Invalid authorized work projection")

    def tool_payload(self):
        if self.audit_id is None:
            raise ValueError("Read projection has no durable audit receipt")
        return {"open_tasks": self.open_tasks, "waiting_tasks": self.waiting_tasks, "record_count": self.record_count,
                "as_of": self.as_of.isoformat(), "source_refs": [{"entity": "query_receipt", "id": str(self.audit_id),
                    "version": 1, "projection_hash": self.source_hash, "as_of": self.as_of.isoformat()}]}
