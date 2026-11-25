from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analytics import Exam, Mark, Scope, Source, Subject, analyze, compare, parse_mark, ranks, trend
from cli import decode, demo, pairs


class GradeTests(unittest.TestCase):
    def setUp(self):
        self.scope = Scope("synthetic", "class-a", "term-a")
        self.subject = Subject("math", Decimal(100))

    def exam(self, scores=("80", "80", "70"), *, exam_id="E1", on=date(2026, 1, 1)):
        students = tuple(f"S{i:03}" for i in range(1, len(scores) + 1))
        marks = tuple(parse_mark(student, self.subject, raw, Source(exam_id, index, 1))
                      for index, (student, raw) in enumerate(zip(students, scores), 2))
        return Exam(exam_id, self.scope, on, (self.subject,), students, marks)

    def test_totals_means_and_competition_ties_are_deterministic(self):
        result = analyze(self.exam())
        self.assertEqual([row.rank for row in result.students], [1, 1, 3])
        self.assertEqual(result.complete_total_mean, Decimal("76.67"))
        self.assertEqual(result.complete_count, 3)
        self.assertEqual(result.subjects[0].ranks, (("S001", 1), ("S002", 1), ("S003", 3)))
        self.assertEqual(result.students[0].marks[0].source, Source("E1", 2, 1))

    def test_zero_is_score_and_missing_states_never_zero_filled(self):
        result = analyze(self.exam(("0", "缺考", "免考", "", "NaN", "101")))
        self.assertEqual(result.complete_count, 1)
        self.assertEqual(result.students[0].rank, 1)
        self.assertEqual(result.students[0].valid_total, Decimal(0))
        self.assertTrue(all(row.rank is None and row.valid_total is None for row in result.students[1:]))
        self.assertEqual(dict(result.subjects[0].states),
                         {"valid": 1, "absent": 1, "excused": 1, "not_entered": 1, "invalid": 2})

    def test_multisubject_partial_total_named_and_excluded_from_total_rank(self):
        language = Subject("language", Decimal(150))
        exam = self.exam(("80", "90"))
        extra = parse_mark("S001", language, "100", Source("B1", 5, 1))
        exam = replace(exam, subjects=(self.subject, language), marks=exam.marks + (extra,))
        result = analyze(exam)
        self.assertEqual((result.students[0].complete_total, result.students[0].valid_mean), (Decimal(180), Decimal("90.00")))
        self.assertEqual((result.students[1].valid_total, result.students[1].complete_total, result.students[1].rank), (Decimal(90), None, None))
        self.assertEqual(result.students[1].marks[0].state, "not_entered")
        self.assertIsNone(result.students[1].marks[0].source)

    def test_round_half_up_only_for_display_ranking_keeps_original_precision(self):
        result = analyze(self.exam(("80.004", "80.003", "80.005")))
        self.assertEqual([row.rank for row in result.students], [2, 3, 1])
        self.assertEqual(result.students[2].valid_mean, Decimal("80.01"))

    def test_invalid_raw_values_remain_invalid_with_provenance(self):
        for raw in ("-1", "Infinity", "sNaN", "bad", "100.0001", "1.00001", "=1+1"):
            with self.subTest(raw=raw):
                mark = parse_mark("S001", self.subject, raw, Source("B1", 2, 1))
                self.assertEqual((mark.state, mark.score, mark.raw), ("invalid", None, raw))
                self.assertIsNotNone(mark.source)

    def test_empty_roster_and_all_missing_have_no_statistics(self):
        for exam in (self.exam(()), self.exam(("", "缺考"))):
            result = analyze(exam)
            self.assertIsNone(result.complete_total_mean)
            self.assertIsNone(result.subjects[0].mean)
            self.assertEqual(result.complete_count, 0)

    def test_duplicate_unknown_and_out_of_scale_marks_rejected(self):
        exam = self.exam()
        for marks in (exam.marks + (exam.marks[0],),
                      (replace(exam.marks[0], student="OTHER"),),
                      (replace(exam.marks[0], subject="unknown"),),
                      (replace(exam.marks[0], score=Decimal(101)),)):
            with self.assertRaises(ValueError):
                replace(exam, marks=marks)

    def test_subject_scope_source_and_mark_types_are_closed(self):
        for maximum in (Decimal(0), Decimal("NaN"), Decimal(-1), Decimal("0.00001"), 100.0):
            with self.assertRaises(ValueError):
                Subject("math", maximum)
        with self.assertRaises(ValueError):
            Source("B1", True, 1)
        with self.assertRaises(ValueError):
            Mark("S001", "math", "valid", Decimal(1), "1", None)
        with self.assertRaises(ValueError):
            Mark("S001", "math", "absent", Decimal(0), "缺考", Source("B1", 1, 1))

    def test_comparison_paired_cohort_recomputes_ranks_and_retains_sources(self):
        before = self.exam(("80", "90", "70"))
        after = self.exam(("95", "90", "缺考", "100"), exam_id="E2", on=date(2026, 2, 1))
        result = compare(before, after)
        self.assertEqual(result["paired_count"], 2)
        self.assertEqual(result["rank_basis"], "common_complete_students_only")
        first = result["rows"][0]
        self.assertEqual((first["delta"], first["before_paired_rank"], first["after_paired_rank"], first["rank_gain"]), (Decimal(15), 2, 1, 1))
        self.assertEqual(len(first["sources"]), 2)
        self.assertEqual([row["status"] for row in result["rows"]], ["paired", "paired", "excluded", "excluded"])

    def test_comparison_no_common_complete_rows_has_zero_sample(self):
        result = compare(self.exam(("缺考",)), self.exam(("80",), exam_id="E2", on=date(2026, 2, 1)))
        self.assertEqual(result["paired_count"], 0)
        self.assertEqual(result["rows"][0]["status"], "excluded")

    def test_cross_scope_scale_subject_and_date_comparisons_refused(self):
        before = self.exam()
        after = self.exam(exam_id="E2", on=date(2026, 2, 1))
        for changed in (replace(after, scope=replace(self.scope, term="other")),
                        replace(after, subjects=(Subject("math", Decimal(150)),)),
                        replace(after, on=before.on), replace(after, exam_id=before.exam_id)):
            self.assertEqual(compare(before, changed)["status"], "not_comparable")

    def test_three_exam_numeric_sequence_and_insufficient_data(self):
        exams = demo()
        result = trend("S001", exams)
        self.assertEqual((result["status"], result["direction"], result["sample_count"]), ("numeric_sequence", "increasing", 3))
        self.assertEqual(trend("S001", exams[:2])["status"], "insufficient_data")
        self.assertEqual(trend("unknown", exams)["status"], "insufficient_data")
        self.assertEqual(trend("S001", tuple(reversed(exams)))["status"], "not_comparable")

    def test_missing_middle_exam_not_silently_skipped(self):
        exams = list(demo())
        exams[1] = replace(exams[1], marks=exams[1].marks[1:])
        self.assertEqual(trend("S001", tuple(exams))["status"], "insufficient_data")

    def test_numeric_decreasing_unchanged_and_mixed(self):
        for scores, direction in (((90, 80, 70), "decreasing"), ((80, 80, 80), "unchanged"), ((80, 90, 80), "mixed")):
            exams = tuple(self.exam((str(score),), exam_id=f"E{i}", on=date(2026, i, 1)) for i, score in enumerate(scores, 1))
            self.assertEqual(trend("S001", exams)["direction"], direction)

    def test_input_order_does_not_change_analysis(self):
        exam = self.exam()
        self.assertEqual(analyze(exam), analyze(replace(exam, marks=tuple(reversed(exam.marks)), students=tuple(reversed(exam.students)))))

    def test_mismatched_raw_score_or_state_cannot_enter_calculation(self):
        exam = self.exam()
        for changed in (replace(exam.marks[0], score=Decimal(90)),
                        replace(exam.marks[0], state="invalid", score=None)):
            with self.assertRaises(ValueError):
                replace(exam, marks=(changed,))

    def test_demo_cli_outputs_actual_calculations(self):
        result = subprocess.run([sys.executable, "cli.py", "--demo"], cwd=Path(__file__).parent,
                                text=True, capture_output=True, check=True)
        output = json.loads(result.stdout)
        self.assertEqual(output["comparison"]["rows"][0]["delta"], "15")
        self.assertEqual(output["trend"]["direction"], "increasing")

    def test_json_cli_reads_explicit_source_and_does_not_write(self):
        fixture = {"exam_id": "E1", "scope": {"workspace": "synthetic", "classroom": "class-a", "term": "term-a"},
                   "on": "2026-01-01", "subjects": [{"subject_id": "math", "maximum": "100"}],
                   "students": ["S001"], "marks": [{"student": "S001", "subject": "math", "raw": "80",
                                                        "source": {"batch": "B1", "row": 2, "version": 1}}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps([fixture]), encoding="utf-8")
            result = subprocess.run([sys.executable, "cli.py", "--file", str(path)], cwd=Path(__file__).parent,
                                    text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout)["analyses"][0]["students"][0]["complete_total"], "80")
            self.assertEqual(list(Path(directory).iterdir()), [path])
        with self.assertRaises(ValueError):
            decode({**fixture, "unknown": True})
        with self.assertRaises(ValueError):
            pairs([("score", "1"), ("score", "2")])


if __name__ == "__main__":
    unittest.main()
