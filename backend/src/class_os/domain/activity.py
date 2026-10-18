"""Closed R1 factual events and manual tasks; never inferred student labels."""
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from uuid import UUID
from types import MappingProxyType
import unicodedata

from .roster import identifiers, name


KINDS = ("attendance_late_fact", "attendance_absent_fact", "leave_requested_fact", "leave_approved_fact",
         "leave_returned_fact", "homework_missing_fact", "homework_submitted_fact", "ordinary_fact",
         "teacher_observation", "discipline_fact", "conversation_fact")
OPEN_STATES = ("not-started", "in-progress", "waiting")
LEAVE_PREDECESSORS = MappingProxyType({"leave_approved_fact": "leave_requested_fact",
                                     "leave_returned_fact": "leave_approved_fact"})


def content(value, *, required=False, maximum=2000):
    if (type(value) is not str or len(value) > maximum or (required and not value.strip())
            or any(unicodedata.category(c) in ("Cf", "Cs") or (unicodedata.category(c) == "Cc" and c not in "\n\t") for c in value)):
        raise ValueError("Invalid manual content")


def instant(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An unambiguous timestamp is required")
    return value.astimezone(timezone.utc)


def version(value):
    if type(value) is not int or value < 1:
        raise ValueError("Invalid expected version")


class Canonical:
    def canonical(self):
        def encode(value):
            if isinstance(value, UUID):
                return str(value)
            if isinstance(value, datetime):
                return instant(value).isoformat()
            return value
        return {key: encode(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class CreateRecord(Canonical):
    command: str
    record_id: UUID
    class_id: UUID
    term_id: UUID
    student_id: UUID
    kind: str
    occurred_at: datetime
    fact_text: str
    observation_text: str
    related_record_id: UUID | None = None

    def __post_init__(self):
        if self.command != "record.create" or self.kind not in KINDS:
            raise ValueError("Unregistered factual event")
        identifiers(self.record_id, self.class_id, self.term_id, self.student_id)
        if self.related_record_id is not None:
            identifiers(self.related_record_id)
        instant(self.occurred_at)
        content(self.fact_text)
        content(self.observation_text)
        if not (self.fact_text.strip() or self.observation_text.strip()):
            raise ValueError("Empty event")
        if self.kind == "teacher_observation" and (self.fact_text or not self.observation_text.strip()):
            raise ValueError("Observation is not an objective fact")
        if self.kind != "teacher_observation" and not self.fact_text.strip():
            raise ValueError("Factual event requires fact text")
        if self.kind in LEAVE_PREDECESSORS and self.related_record_id is None:
            raise ValueError("Leave follow-up requires its preceding fact")


@dataclass(frozen=True)
class ReviseRecord(Canonical):
    command: str
    record_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    fact_text: str
    observation_text: str
    reason: str

    def __post_init__(self):
        if self.command not in ("record.correct", "record.supersede"):
            raise ValueError("Unregistered record revision")
        identifiers(self.record_id, self.class_id, self.term_id)
        version(self.expected_version)
        content(self.fact_text)
        content(self.observation_text)
        content(self.reason, required=True, maximum=500)
        if not (self.fact_text.strip() or self.observation_text.strip()):
            raise ValueError("Empty revision")


@dataclass(frozen=True)
class CreateTask(Canonical):
    command: str
    task_id: UUID
    class_id: UUID
    term_id: UUID
    title: str
    due_at: datetime | None = None
    student_id: UUID | None = None
    source_record_id: UUID | None = None

    def __post_init__(self):
        if self.command != "task.create":
            raise ValueError("Unregistered task")
        identifiers(self.task_id, self.class_id, self.term_id)
        name(self.title)
        for optional in (self.student_id, self.source_record_id):
            if optional is not None:
                identifiers(optional)
        if self.due_at is not None:
            instant(self.due_at)


@dataclass(frozen=True)
class ChangeTask(Canonical):
    command: str
    task_id: UUID
    class_id: UUID
    term_id: UUID
    expected_version: int
    status: str
    evidence: str = ""
    title: str | None = None
    due_at: datetime | None = None
    change_due_date: bool = False

    def __post_init__(self):
        identifiers(self.task_id, self.class_id, self.term_id)
        version(self.expected_version)
        content(self.evidence, maximum=500)
        if type(self.change_due_date) is not bool:
            raise ValueError("Explicit deadline-change flag required")
        if self.title is not None:
            name(self.title)
        if self.due_at is not None:
            instant(self.due_at)
            if not self.change_due_date:
                raise ValueError("Implicit deadline change rejected")
        if self.command != "task.update" and (self.title is not None or self.change_due_date):
            raise ValueError("Terminal transition cannot edit task content")
        if not ((self.command == "task.update" and self.status in OPEN_STATES)
                or (self.command == "task.complete" and self.status == "done" and self.evidence.strip())
                or (self.command == "task.cancel" and self.status == "cancelled" and self.evidence.strip())):
            raise ValueError("Invalid task transition")

    def canonical(self):
        values = super().canonical()
        if self.title is None:
            values.pop("title")
        if not self.change_due_date:
            values.pop("due_at")
            values.pop("change_due_date")
        return values


COMMAND_TYPES = {"record.create": CreateRecord, "record.correct": ReviseRecord, "record.supersede": ReviseRecord,
                 "task.create": CreateTask, "task.update": ChangeTask, "task.complete": ChangeTask, "task.cancel": ChangeTask}


def decode_activity(payload):
    model = COMMAND_TYPES.get(payload.get("command")) if type(payload) is dict else None
    if model is None:
        raise ValueError("Unknown activity payload")
    known = {item.name for item in fields(model)}
    optional = {"title", "due_at", "change_due_date"} if model is ChangeTask else set()
    if not known - optional <= set(payload) or not set(payload) <= known:
        raise ValueError("Unknown activity payload")
    values = dict(payload)
    for key in ("record_id", "task_id", "class_id", "term_id", "student_id", "related_record_id", "source_record_id"):
        if key in values and values[key] is not None:
            values[key] = UUID(values[key])
    for key in ("occurred_at", "due_at"):
        if key in values and values[key] is not None:
            values[key] = datetime.fromisoformat(values[key])
    return model(**values)
