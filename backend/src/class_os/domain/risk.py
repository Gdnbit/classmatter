"""Closed R1 risk table. Assessment is NOT authentication or write permission.

Owning application handlers must derive these inputs from validated canonical
payloads, not copy client/model risk claims. A Gateway must still apply admission,
authorization, version/idempotency, approval and atomic audit before any write.
"""
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from types import MappingProxyType


class Risk(IntEnum):
    W1 = 1
    W2 = 2
    X = 3


class DataClass(IntEnum):
    D0 = 0
    D1 = 1
    D2 = 2
    D3 = 3
    D4 = 4


class Command(StrEnum):
    CLASS_CREATE = "class.create"
    CLASS_UPDATE = "class.update"
    CLASS_ARCHIVE = "class.archive"
    TERM_UPDATE = "term.update"
    STUDENT_CREATE = "student.create"
    STUDENT_NAME = "student.update_name"
    STUDENT_IDENTIFIER = "student.update_identifier"
    STUDENT_DEACTIVATE = "student.deactivate"
    RECORD_CREATE = "record.create"
    RECORD_CORRECT = "record.correct"
    RECORD_SUPERSEDE = "record.supersede"
    TASK_CREATE = "task.create"
    TASK_UPDATE = "task.update"
    TASK_COMPLETE = "task.complete"
    TASK_CANCEL = "task.cancel"
    EXIT_EXPORT = "exit_export.create"
    MODEL_SAVE = "model_configuration.save"
    MODEL_CLEAR = "model_configuration.clear"


FLOORS = MappingProxyType({
    Command.CLASS_CREATE: Risk.W2, Command.CLASS_UPDATE: Risk.W2, Command.CLASS_ARCHIVE: Risk.W2,
    Command.TERM_UPDATE: Risk.W2,
    Command.STUDENT_CREATE: Risk.W1, Command.STUDENT_IDENTIFIER: Risk.W2, Command.STUDENT_DEACTIVATE: Risk.W2,
    Command.STUDENT_NAME: Risk.W2,
    Command.RECORD_CREATE: Risk.W1, Command.RECORD_CORRECT: Risk.W2, Command.RECORD_SUPERSEDE: Risk.W2,
    Command.TASK_CREATE: Risk.W1, Command.TASK_UPDATE: Risk.W1, Command.TASK_COMPLETE: Risk.W1,
    Command.TASK_CANCEL: Risk.W1, Command.EXIT_EXPORT: Risk.W2,
    Command.MODEL_SAVE: Risk.W2, Command.MODEL_CLEAR: Risk.W2,
})


@dataclass(frozen=True)
class Assessment:
    command: Command
    data_class: DataClass = DataClass.D2
    record_kind: str | None = None
    affected_count: int = 1
    attachments: bool = False
    external: bool = False
    irreversible: bool = False
    authenticated: bool = True


@dataclass(frozen=True)
class Decision:
    level: Risk
    admitted: bool  # only R1 shape eligibility, never authorization
    reasons: tuple[str, ...]
    policy_version: str = "r1.3"

    @property
    def requires_approval(self):
        return self.level >= Risk.W2

    @property
    def requires_recent_reauthentication(self):
        return self.level == Risk.X


def evaluate(assessment: Assessment) -> Decision:
    if (type(assessment) is not Assessment or type(assessment.command) is not Command
            or type(assessment.data_class) is not DataClass or type(assessment.affected_count) is not int
            or assessment.affected_count < 1
            or any(type(value) is not bool for value in (assessment.attachments, assessment.external,
                                                        assessment.irreversible, assessment.authenticated))
            or assessment.record_kind not in (None, "discipline", "conversation", "ordinary")
            or (assessment.record_kind is not None and assessment.command not in
                (Command.RECORD_CREATE, Command.RECORD_CORRECT, Command.RECORD_SUPERSEDE))):
        raise ValueError("Invalid canonical risk assessment")
    level = FLOORS[assessment.command]
    admitted = True
    reasons = ["static_floor"]
    if assessment.data_class >= DataClass.D3:
        level = max(level, Risk.W2)
        reasons.append("sensitive_data")
        if assessment.command in (Command.STUDENT_CREATE, Command.STUDENT_NAME, Command.STUDENT_IDENTIFIER, Command.STUDENT_DEACTIVATE):
            admitted = False
            reasons.append("roster_d3_not_in_r1")
    if assessment.record_kind in ("discipline", "conversation"):
        level = max(level, Risk.W2)
        reasons.append("sensitive_record_kind")
    for applies, reason in ((assessment.attachments, "attachments_not_in_r1"),
                            (assessment.affected_count > 1, "bulk_not_in_r1"),
                            (assessment.data_class == DataClass.D4, "d4_not_in_r1")):
        if applies:
            level = max(level, Risk.W2)
            admitted = False
            reasons.append(reason)
    for applies, reason in ((assessment.external, "external_not_in_r1"),
                            (assessment.irreversible, "irreversible_not_in_r1")):
        if applies:
            level = Risk.X
            admitted = False
            reasons.append(reason)
    if not assessment.authenticated:
        level = max(level, Risk.W2)
        admitted = False
        reasons.append("authentication_required")
    return Decision(level, admitted, tuple(reasons))
