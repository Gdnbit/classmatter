"""Closed, manual R1 roster commands; no guardian/import/merge/generic patch."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
import unicodedata
from typing import TYPE_CHECKING
from uuid import UUID
from dataclasses import asdict, fields

if TYPE_CHECKING:
    from .activity import CreateRecord, ReviseRecord, CreateTask, ChangeTask
    from .exit_package import CreateExitExport
    from .model_control import ModelControl
    from .conversation_control import InitializeConversationControl, ClearConversation
    from .conversation_exit import CreateConversationExit
    from .source_transfer import SealConversationSource


def name(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 80 or value != value.strip()
            or any(unicodedata.category(character) in ("Cc", "Cf", "Cs") for character in value)):
        raise ValueError("Invalid display name")


def identifiers(*values):
    if any(type(value) is not UUID for value in values):
        raise ValueError("Invalid entity identifier")


@dataclass(frozen=True)
class CreateClass:
    class_id: UUID
    term_id: UUID
    name: str
    term_name: str
    start_date: date
    end_date: date

    def __post_init__(self):
        identifiers(self.class_id, self.term_id)
        name(self.name)
        name(self.term_name)
        if type(self.start_date) is not date or type(self.end_date) is not date or self.start_date >= self.end_date:
            raise ValueError("Invalid academic term")

    def canonical(self):
        return {"command": "class.create", "class_id": str(self.class_id), "term_id": str(self.term_id),
                "name": self.name, "term_name": self.term_name,
                "start_date": self.start_date.isoformat(), "end_date": self.end_date.isoformat()}


@dataclass(frozen=True)
class CreateStudent:
    student_id: UUID
    class_id: UUID
    term_id: UUID
    expected_class_version: int
    name: str

    def __post_init__(self):
        identifiers(self.student_id, self.class_id, self.term_id)
        name(self.name)
        if type(self.expected_class_version) is not int or self.expected_class_version < 1:
            raise ValueError("Invalid resource version")

    def canonical(self):
        return {"command": "student.create", "student_id": str(self.student_id), "class_id": str(self.class_id),
                "term_id": str(self.term_id), "expected_class_version": self.expected_class_version, "name": self.name}


def decode(payload):
    if type(payload) is not dict:
        raise ValueError("Unknown roster payload")
    kind = payload.get("command")
    if kind in ("model_configuration.save", "model_configuration.clear"):
        from .model_control import ModelControl
        if set(payload) != {"command", "candidate_id", "expected_version", "protocol", "model", "base_url"}:
            raise ValueError("Unknown model control payload")
        return ModelControl(**{**payload, "candidate_id": UUID(payload["candidate_id"])})
    if kind == "exit_export.create" and set(payload) == {"command", "export_id", "expected_core_hash"}:
        from .exit_package import CreateExitExport
        return CreateExitExport(UUID(payload["export_id"]), payload["expected_core_hash"])
    if kind == "class.create" and set(payload) == {"command", "class_id", "term_id", "name", "term_name", "start_date", "end_date"}:
        return CreateClass(UUID(payload["class_id"]), UUID(payload["term_id"]), payload["name"], payload["term_name"],
                           date.fromisoformat(payload["start_date"]), date.fromisoformat(payload["end_date"]))
    if kind == "student.create" and set(payload) == {"command", "student_id", "class_id", "term_id", "expected_class_version", "name"}:
        return CreateStudent(UUID(payload["student_id"]), UUID(payload["class_id"]), UUID(payload["term_id"]),
                             payload["expected_class_version"], payload["name"])
    if kind in ROSTER_MUTATIONS:
        model = ROSTER_MUTATIONS[kind]
        allowed = {item.name for item in fields(model)}
        legacy = allowed - {"supersedes_identifier_id"} if model is UpdateIdentifier else allowed
        if set(payload) not in (allowed, legacy):
            raise ValueError("Unknown roster payload")
        values = dict(payload)
        for key in ("class_id", "term_id", "student_id", "identifier_id", "supersedes_identifier_id"):
            if key in values and values[key] is not None:
                values[key] = UUID(values[key])
        for key in ("valid_from", "valid_to"):
            if key in values and values[key] is not None:
                values[key] = datetime.fromisoformat(values[key])
        if model is ChangeTerm:
            for key in ("previous_start_date", "start_date", "previous_end_date", "end_date"):
                values[key] = date.fromisoformat(values[key])
        return model(**values)
    from .activity import decode_activity
    return decode_activity(payload)


class RosterCanonical:
    def canonical(self):
        return {key: value.isoformat() if isinstance(value, date) else str(value) if isinstance(value, UUID) else value
                for key, value in asdict(self).items()}


@dataclass(frozen=True)
class ChangeClass(RosterCanonical):
    command: str
    class_id: UUID
    term_id: UUID
    expected_version: int
    name: str

    def __post_init__(self):
        identifiers(self.class_id, self.term_id)
        name(self.name)
        if self.command not in ("class.update", "class.archive") or type(self.expected_version) is not int or self.expected_version < 1:
            raise ValueError("Invalid class mutation")


@dataclass(frozen=True)
class ChangeTerm(RosterCanonical):
    command: str
    class_id: UUID
    term_id: UUID
    expected_version: int
    previous_name: str
    name: str
    previous_start_date: date
    start_date: date
    previous_end_date: date
    end_date: date

    def __post_init__(self):
        identifiers(self.class_id, self.term_id)
        name(self.previous_name)
        name(self.name)
        if (self.command != "term.update" or type(self.expected_version) is not int
                or not 1 <= self.expected_version < 2147483647
                or any(type(value) is not date for value in (self.previous_start_date, self.start_date,
                                                           self.previous_end_date, self.end_date))
                or self.previous_start_date >= self.previous_end_date or self.start_date >= self.end_date
                or (self.previous_name, self.previous_start_date, self.previous_end_date)
                   == (self.name, self.start_date, self.end_date)):
            raise ValueError("Invalid academic term correction")


@dataclass(frozen=True)
class ChangeStudentName(RosterCanonical):
    command: str
    student_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    previous_name: str
    name: str

    def __post_init__(self):
        identifiers(self.student_id, self.class_id, self.term_id)
        name(self.previous_name)
        name(self.name)
        if (self.command != "student.update_name" or type(self.expected_version) is not int
                or self.expected_version < 1 or self.name == self.previous_name):
            raise ValueError("Invalid student name correction")


@dataclass(frozen=True)
class DeactivateStudent(RosterCanonical):
    command: str
    student_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int

    def __post_init__(self):
        identifiers(self.student_id, self.class_id, self.term_id)
        if self.command != "student.deactivate" or type(self.expected_version) is not int or self.expected_version < 1:
            raise ValueError("Invalid student mutation")


@dataclass(frozen=True)
class UpdateIdentifier(RosterCanonical):
    command: str
    identifier_id: UUID
    student_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    authority: str
    identifier_type: str
    value: str
    valid_from: datetime
    valid_to: datetime | None = None
    supersedes_identifier_id: UUID | None = None

    def __post_init__(self):
        from .temporal import Interval
        identifiers(self.identifier_id, self.student_id, self.class_id, self.term_id)
        if self.supersedes_identifier_id is not None:
            identifiers(self.supersedes_identifier_id)
            if self.supersedes_identifier_id == self.identifier_id:
                raise ValueError("An identifier cannot replace itself")
        name(self.authority)
        name(self.value)
        if (self.command != "student.update_identifier" or self.identifier_type not in ("school_number", "exam_number")
                or type(self.expected_version) is not int or self.expected_version < 1):
            raise ValueError("Invalid identifier mutation")
        if not isinstance(self.valid_from, datetime) or self.valid_from.tzinfo is None:
            raise ValueError("Invalid identifier interval")
        if self.valid_to is not None:
            Interval(self.valid_from, self.valid_to)

    def canonical(self):
        values = super().canonical()
        if self.supersedes_identifier_id is None:
            values.pop("supersedes_identifier_id")
        return values


ROSTER_MUTATIONS = {"class.update": ChangeClass, "class.archive": ChangeClass,
                    "term.update": ChangeTerm,
                    "student.update_name": ChangeStudentName,
                    "student.deactivate": DeactivateStudent, "student.update_identifier": UpdateIdentifier}


@dataclass(frozen=True)
class Proposal:
    proposal_id: UUID
    payload_hash: str
    risk: str
    expires_at: datetime
    command: CreateClass | CreateStudent | ChangeClass | ChangeTerm | ChangeStudentName | DeactivateStudent | UpdateIdentifier | CreateRecord | ReviseRecord | CreateTask | ChangeTask | CreateExitExport | ModelControl | InitializeConversationControl | ClearConversation | CreateConversationExit | SealConversationSource


@dataclass(frozen=True)
class Receipt:
    receipt_id: UUID
    resource_id: UUID
    version: int


@dataclass(frozen=True)
class CommandStatus:
    proposal_id: UUID
    payload_hash: str
    status: str
    receipt: Receipt | None


@dataclass(frozen=True)
class StudentView:
    student_id: UUID
    name: str
    version: int
    status: str = "active"


@dataclass(frozen=True)
class ClassView:
    class_id: UUID
    term_id: UUID
    name: str
    term_name: str
    version: int


@dataclass(frozen=True)
class TermMetadata:
    class_id: UUID
    term_id: UUID
    name: str
    start_date: date
    end_date: date
    version: int
