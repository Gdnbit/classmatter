import argparse
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from analytics import Exam, Scope, Source, Subject, analyze, compare, parse_mark, trend


def pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def decode(value):
    if type(value) is not dict or set(value) != {"exam_id", "scope", "on", "subjects", "students", "marks"}:
        raise ValueError("closed exam JSON shape required")
    subjects = tuple(Subject(item["subject_id"], Decimal(item["maximum"])) for item in value["subjects"]
                     if set(item) == {"subject_id", "maximum"} and type(item["maximum"]) is str)
    if len(subjects) != len(value["subjects"]):
        raise ValueError("closed subject shape with string maximum required")
    by_id = {subject.subject_id: subject for subject in subjects}
    marks = []
    for mark in value["marks"]:
        if set(mark) != {"student", "subject", "raw", "source"}:
            raise ValueError("closed mark shape required")
        marks.append(parse_mark(mark["student"], by_id[mark["subject"]], mark["raw"], Source(**mark["source"])))
    return Exam(value["exam_id"], Scope(**value["scope"]), date.fromisoformat(value["on"]),
                subjects, tuple(value["students"]), tuple(marks))


def demo():
    scope = Scope("synthetic", "class-a", "term-a")
    subject = Subject("math", Decimal(100))
    return tuple(Exam(f"E{index}", scope, date(2026, index, 1), (subject,), ("S001", "S002"),
                      (parse_mark("S001", subject, str(score), Source(f"B{index}", 2, 1)),
                       parse_mark("S002", subject, "90", Source(f"B{index}", 3, 1))))
                 for index, score in enumerate((80, 90, 95), 1))


def main():
    parser = argparse.ArgumentParser(description="Synthetic deterministic grade analysis and source evidence")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--file", type=Path, help="JSON array of1..20 synthetic exams")
    inputs.add_argument("--demo", action="store_true")
    parser.add_argument("--student", default="S001", help="stable ID for numeric sequence")
    args = parser.parse_args()
    try:
        if args.demo:
            exams = demo()
        else:
            if args.file.stat().st_size > 2_000_000:
                raise ValueError("exam JSON exceeds size limit")
            values = json.loads(args.file.read_text(encoding="utf-8"), object_pairs_hook=pairs)
            if type(values) is not list or not 1 <= len(values) <= 20:
                raise ValueError("1..20 exams required")
            exams = tuple(decode(value) for value in values)
        output = {"analyses": tuple(asdict(analyze(exam)) for exam in exams),
                  "comparison": compare(exams[0], exams[-1]) if len(exams) >= 2 else None,
                  "trend": trend(args.student, exams)}
        print(json.dumps(output, ensure_ascii=False,
                         default=lambda value: asdict(value) if isinstance(value, Source) else str(value)))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
