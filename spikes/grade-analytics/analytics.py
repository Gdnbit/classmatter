"""Versioned deterministic synthetic grade calculations, never model-generated."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re

RULE = "synthetic-grade.v1"
STATES = ("valid", "absent", "excused", "not_entered", "invalid")


def identity(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise ValueError("synthetic stable identifier required")


def numeric(value):
    return (type(value) is Decimal and value.is_finite() and value.as_tuple().exponent >= -4
            and 0 <= value <= 100_000)


@dataclass(frozen=True)
class Scope:
    workspace: str
    classroom: str
    term: str

    def __post_init__(self):
        for value in (self.workspace, self.classroom, self.term):
            identity(value)


@dataclass(frozen=True)
class Source:
    batch: str
    row: int
    version: int

    def __post_init__(self):
        identity(self.batch)
        if any(type(value) is not int or value < 1 for value in (self.row, self.version)):
            raise ValueError("positive source row/version required")


@dataclass(frozen=True)
class Subject:
    subject_id: str
    maximum: Decimal

    def __post_init__(self):
        identity(self.subject_id)
        if not numeric(self.maximum) or self.maximum == 0:
            raise ValueError("maximum must be positive finite Decimal with <=4 fractional places")


@dataclass(frozen=True)
class Mark:
    student: str
    subject: str
    state: str
    score: Decimal | None
    raw: str
    source: Source | None

    def __post_init__(self):
        identity(self.student)
        identity(self.subject)
        if self.state not in STATES or type(self.raw) is not str or len(self.raw) > 128:
            raise ValueError("invalid mark state/raw")
        if self.state == "valid":
            if not numeric(self.score) or type(self.source) is not Source:
                raise ValueError("valid scores need finite Decimal and provenance")
        elif self.score is not None:
            raise ValueError("non-score states cannot contain a numeric score")
        if self.source is not None and type(self.source) is not Source:
            raise ValueError("typed source required")
        if self.state != "not_entered" and self.source is None:
            raise ValueError("entered values require provenance")


def parse_mark(student: str, subject: Subject, raw: str, source: Source) -> Mark:
    if type(raw) is not str or len(raw) > 128:
        raise ValueError("bounded raw string required")
    text = raw.strip()
    special = {"": "not_entered", "缺考": "absent", "免考": "excused"}
    state, score = special.get(text, "valid"), None
    if state == "valid":
        try:
            score = Decimal(text)
            if not numeric(score) or score > subject.maximum:
                raise InvalidOperation
        except InvalidOperation:
            state, score = "invalid", None
    return Mark(student, subject.subject_id, state, score, raw, source)


@dataclass(frozen=True)
class Exam:
    exam_id: str
    scope: Scope
    on: date
    subjects: tuple[Subject, ...]
    students: tuple[str, ...]
    marks: tuple[Mark, ...]

    def __post_init__(self):
        identity(self.exam_id)
        if type(self.scope) is not Scope or type(self.on) is not date:
            raise ValueError("typed exam scope/date required")
        if (type(self.subjects) is not tuple or not 1 <= len(self.subjects) <= 20
                or any(type(value) is not Subject for value in self.subjects)
                or len({value.subject_id for value in self.subjects}) != len(self.subjects)):
            raise ValueError("1..20 unique subjects required")
        if type(self.students) is not tuple or len(self.students) > 2000 or len(set(self.students)) != len(self.students):
            raise ValueError("unique bounded roster required")
        for student in self.students:
            identity(student)
        subjects = {value.subject_id: value for value in self.subjects}
        if type(self.marks) is not tuple or len(self.marks) > 40_000:
            raise ValueError("bounded typed marks required")
        keys = set()
        for mark in self.marks:
            if type(mark) is not Mark or mark.student not in self.students or mark.subject not in subjects:
                raise ValueError("unknown student/subject")
            key = mark.student, mark.subject
            if key in keys or (mark.state == "valid" and mark.score > subjects[mark.subject].maximum):
                raise ValueError("duplicate or out-of-scale score")
            if mark.source is None:
                if mark.state != "not_entered" or mark.raw.strip():
                    raise ValueError("source-free entry must be truly missing")
            elif parse_mark(mark.student, subjects[mark.subject], mark.raw, mark.source) != mark:
                raise ValueError("score/state must agree with the original raw source")
            keys.add(key)


def mean(values):
    values = tuple(values)
    if not values:
        return None
    with localcontext() as context:
        context.prec = 40
        return (sum(values, Decimal(0)) / len(values)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ranks(values: dict[str, Decimal]) -> dict[str, int]:
    ordered = sorted(values, key=lambda key: (-values[key], key))
    result, rank, previous = {}, 0, None
    for position, student in enumerate(ordered, 1):
        if values[student] != previous:
            rank = position
        result[student], previous = rank, values[student]
    return result


@dataclass(frozen=True)
class StudentResult:
    student: str
    valid_count: int
    valid_total: Decimal | None
    valid_mean: Decimal | None
    complete_total: Decimal | None
    rank: int | None
    marks: tuple[Mark, ...]


@dataclass(frozen=True)
class SubjectResult:
    subject: str
    valid_count: int
    mean: Decimal | None
    minimum: Decimal | None
    maximum: Decimal | None
    states: tuple[tuple[str, int], ...]
    ranks: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Analysis:
    rule: str
    exam: str
    scope: Scope
    on: date
    roster_count: int
    complete_count: int
    complete_total_mean: Decimal | None
    students: tuple[StudentResult, ...]
    subjects: tuple[SubjectResult, ...]


def analyze(exam: Exam) -> Analysis:
    lookup = {(mark.student, mark.subject): mark for mark in exam.marks}
    rows = []
    for student in sorted(exam.students):
        marks = tuple(lookup.get((student, subject.subject_id),
                                Mark(student, subject.subject_id, "not_entered", None, "", None))
                      for subject in sorted(exam.subjects, key=lambda value: value.subject_id))
        values = [mark.score for mark in marks if mark.state == "valid"]
        total = sum(values, Decimal(0)) if values else None
        rows.append(StudentResult(student, len(values), total, mean(values),
                                  total if len(values) == len(exam.subjects) else None, None, marks))
    totals = {row.student: row.complete_total for row in rows if row.complete_total is not None}
    total_ranks = ranks(totals)
    rows = tuple(StudentResult(row.student, row.valid_count, row.valid_total, row.valid_mean,
                               row.complete_total, total_ranks.get(row.student), row.marks) for row in rows)
    subjects = []
    for subject in sorted(exam.subjects, key=lambda value: value.subject_id):
        marks = [mark for row in rows for mark in row.marks if mark.subject == subject.subject_id]
        values = {mark.student: mark.score for mark in marks if mark.state == "valid"}
        counts = Counter(mark.state for mark in marks)
        subjects.append(SubjectResult(subject.subject_id, len(values), mean(values.values()),
                                      min(values.values(), default=None), max(values.values(), default=None),
                                      tuple((state, counts[state]) for state in STATES), tuple(sorted(ranks(values).items()))))
    return Analysis(RULE, exam.exam_id, exam.scope, exam.on, len(rows), len(totals), mean(totals.values()), rows, tuple(subjects))


def comparable(before: Exam, after: Exam) -> str | None:
    if before.scope != after.scope:
        return "scope_changed"
    if before.on >= after.on or before.exam_id == after.exam_id:
        return "exam_order_invalid"
    if {item.subject_id: item.maximum for item in before.subjects} != {item.subject_id: item.maximum for item in after.subjects}:
        return "subject_or_scale_changed"
    return None


def compare(before: Exam, after: Exam) -> dict:
    reason = comparable(before, after)
    if reason:
        return {"rule": RULE, "status": "not_comparable", "reason": reason, "before": before.exam_id, "after": after.exam_id}
    old, new = analyze(before), analyze(after)
    old_rows, new_rows = {row.student: row for row in old.students}, {row.student: row for row in new.students}
    paired = sorted(student for student in old_rows.keys() & new_rows.keys()
                    if old_rows[student].complete_total is not None and new_rows[student].complete_total is not None)
    old_rank = ranks({student: old_rows[student].complete_total for student in paired})
    new_rank = ranks({student: new_rows[student].complete_total for student in paired})
    rows = []
    for student in sorted(old_rows.keys() | new_rows.keys()):
        if student in paired:
            rows.append({"student": student, "status": "paired", "before_total": old_rows[student].complete_total,
                         "after_total": new_rows[student].complete_total,
                         "delta": new_rows[student].complete_total - old_rows[student].complete_total,
                         "before_paired_rank": old_rank[student], "after_paired_rank": new_rank[student],
                         "rank_gain": old_rank[student] - new_rank[student],
                         "sources": tuple(mark.source for row in (old_rows[student], new_rows[student]) for mark in row.marks)})
        else:
            rows.append({"student": student, "status": "excluded", "reason": "missing_student_or_incomplete_exam"})
    return {"rule": RULE, "status": "comparable", "before": before.exam_id, "after": after.exam_id,
            "before_roster": len(old_rows), "after_roster": len(new_rows), "paired_count": len(paired),
            "rank_basis": "common_complete_students_only", "rows": tuple(rows)}


def trend(student: str, exams: tuple[Exam, ...]) -> dict:
    identity(student)
    if len(exams) < 3:
        return {"rule": RULE, "status": "insufficient_data", "required_exams": 3}
    if len(exams) > 20 or len({exam.exam_id for exam in exams}) != len(exams):
        raise ValueError("at most20 distinct ordered exams required")
    if any(comparable(left, right) for left, right in zip(exams, exams[1:])):
        return {"rule": RULE, "status": "not_comparable"}
    values, sources = [], []
    for exam in exams:
        row = next((row for row in analyze(exam).students if row.student == student), None)
        if row is None or row.complete_total is None:
            return {"rule": RULE, "status": "insufficient_data", "reason": "missing_or_incomplete_exam"}
        values.append(row.complete_total)
        sources.append(tuple(mark.source for mark in row.marks))
    deltas = [right - left for left, right in zip(values, values[1:])]
    direction = ("increasing" if all(value > 0 for value in deltas) else
                 "decreasing" if all(value < 0 for value in deltas) else
                 "unchanged" if all(value == 0 for value in deltas) else "mixed")
    return {"rule": RULE, "status": "numeric_sequence", "direction": direction,
            "student": student, "sample_count": len(values), "exams": tuple(exam.exam_id for exam in exams),
            "totals": tuple(values), "sources": tuple(sources)}
