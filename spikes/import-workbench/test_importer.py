from dataclasses import asdict
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from importer import GradeCandidate, RosterCandidate, load, preview, suggest


def workbook(rows=None, *, shared=False, formula=False, extra=None, sheets=1):
    rows = rows or [["学号", "姓名"], ["S001", "合成学生01"]]
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' +
                         ''.join(f'<sheet name="Sheet{i}" r:id="r{i}"/>' for i in range(1, sheets + 1)) + '</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships>' + ''.join(
            f'<Relationship Id="r{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, sheets + 1)) + '</Relationships>')
        strings, xmlrows = [], []
        for row_index, values in enumerate(rows, 1):
            cells = []
            for col, value in enumerate(values):
                coordinate = f'{chr(65+col)}{row_index}'
                if value is None:
                    continue
                if shared:
                    strings.append(value)
                    cell = f'<c r="{coordinate}" t="s"><v>{len(strings)-1}</v></c>'
                else:
                    cell = f'<c r="{coordinate}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                if formula and row_index == 2 and col == 1:
                    cell = f'<c r="{coordinate}"><f>1+1</f><v>2</v></c>'
                cells.append(cell)
            xmlrows.append(f'<row r="{row_index}">' + ''.join(cells) + '</row>')
        for i in range(1, sheets + 1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", '<worksheet><sheetData>' + ''.join(xmlrows) + '</sheetData></worksheet>')
        if shared:
            archive.writestr("xl/sharedStrings.xml", '<sst>' + ''.join(f'<si><t>{escape(value)}</t></si>' for value in strings) + '</sst>')
        for key, value in (extra or {}).items():
            archive.writestr(key, value)
    return output.getvalue()


class ImportTests(unittest.TestCase):
    def roster(self, payload, **kwargs):
        table = load(payload, "csv")
        return preview(table, "roster", {"student_id": 0, "name": 1}, **kwargs)

    def test_csv_bom_headers_mapping_and_typed_source(self):
        table = load("\ufeff学号,姓名\r\nS001,合成学生01\r\n".encode(), "csv")
        mapping = suggest(tuple(cell.text for cell in table.rows[0][1]))
        result = preview(table, "roster", mapping)
        candidate = result.rows[0].candidate
        self.assertIsInstance(candidate, RosterCandidate)
        self.assertEqual((candidate.student_id, candidate.source.row), ("S001", 2))
        self.assertEqual(len(candidate.source.fingerprint), 64)
        self.assertEqual(dict(result.counts)["add"], 1)

    def test_empty_bad_encoding_and_unsupported_inputs(self):
        for payload, kind in ((b"", "csv"), (b"\xff", "csv"), (b"text", "xls"), (b"bad", "xlsx"), (b"a\x00b", "csv")):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                load(payload, kind)

    def test_explicit_encoding_and_quoted_multiline_source_start(self):
        table = load('学号,姓名\nS001,"合成\n学生"\nS002,合成学生02'.encode("gb18030"), "csv", encoding="gb18030")
        result = preview(table, "roster", {"student_id": 0, "name": 1})
        self.assertEqual([row.row for row in result.rows], [2, 4])
        self.assertIn("\n", result.rows[0].candidate.name)

    def test_missing_headers_missing_columns_and_duplicate_mapping(self):
        table = load(b"id,name\nS001,Example", "csv")
        for mapping in ({"student_id": 0}, {"student_id": 0, "name": 9}, {"student_id": 0, "name": 0}):
            with self.assertRaises(ValueError):
                preview(table, "roster", mapping)
        with self.assertRaises(ValueError):
            preview(load(b"\n", "csv"), "roster", {"student_id": 0, "name": 1})
        self.assertNotIn("name", suggest(("姓名", "name")))

    def test_explicit_header_and_remapping(self):
        table = load("合成资料\n姓名,学号\n合成学生01,S001".encode(), "csv")
        result = preview(table, "roster", {"student_id": 1, "name": 0}, header_row=2)
        self.assertEqual((result.rows[0].row, result.rows[0].candidate.student_id), (3, "S001"))

    def test_duplicate_rows_all_conflict_without_releasable_candidate(self):
        result = self.roster("学号,姓名\nS001,合成学生01\nS001,合成学生02".encode())
        self.assertEqual([row.action for row in result.rows], ["conflict", "conflict"])
        self.assertTrue(all(row.candidate is None for row in result.rows))

    def test_add_update_unchanged_invalid_and_skipped_counts(self):
        payload = "学号,姓名\nS001,合成学生01\nS002,新合成名\nS003,合成学生03\nS004,\n,\n".encode()
        result = self.roster(payload, roster={"S001": "合成学生01", "S002": "旧合成名"})
        self.assertEqual([row.action for row in result.rows], ["unchanged", "update", "add", "invalid", "skipped"])
        self.assertEqual(sum(dict(result.counts).values()), 5)

    def test_name_does_not_merge_distinct_student_ids(self):
        result = self.roster("学号,姓名\nS001,同名合成\nS002,同名合成".encode())
        self.assertEqual([row.action for row in result.rows], ["add", "add"])

    def test_formula_text_injection_is_a_row_error(self):
        result = self.roster('学号,姓名\nS001,=HYPERLINK("fake")'.encode())
        self.assertIn("name:formula_refused", result.rows[0].errors)
        self.assertIsNone(result.rows[0].candidate)

    def test_grade_states_zero_invalid_and_unmatched_student(self):
        payload = "学号,考试,科目,成绩\nS001,合成考试,数学,0\nS002,合成考试,数学,缺考\nS003,合成考试,数学,免考\nS004,合成考试,数学,\nS005,合成考试,数学,NaN\nS006,合成考试,数学,101\nUNKNOWN,合成考试,数学,80".encode()
        table = load(payload, "csv")
        result = preview(table, "grades", suggest(tuple(cell.text for cell in table.rows[0][1])),
                         roster={f"S{i:03}": f"合成学生{i:02}" for i in range(1, 7)})
        self.assertTrue(all(isinstance(row.candidate, GradeCandidate) for row in result.rows[:4]))
        self.assertEqual([row.candidate.state for row in result.rows[:4]], ["valid", "absent", "excused", "not_entered"])
        self.assertEqual(result.rows[0].candidate.score, Decimal(0))
        self.assertEqual([row.action for row in result.rows[4:]], ["invalid"] * 3)

    def test_grade_duplicate_key_and_existing_grade_projection(self):
        table = load(b"student_id,exam,subject,score\nS001,E1,math,80\nS002,E1,math,90", "csv")
        result = preview(table, "grades", suggest(tuple(cell.text for cell in table.rows[0][1])),
                         roster={"S001": "A", "S002": "B"}, grades={("S001", "E1", "math"): ("valid", Decimal(80))})
        self.assertEqual([row.action for row in result.rows], ["unchanged", "add"])

    def test_xlsx_inline_shared_and_sparse_cells(self):
        for shared in (False, True):
            table = load(workbook(shared=shared), "xlsx")
            result = preview(table, "roster", {"student_id": 0, "name": 1})
            self.assertEqual(result.rows[0].candidate.name, "合成学生01")
            self.assertEqual(result.rows[0].candidate.source.sheet, "Sheet1")
        table = load(workbook([["学号", "unused", "姓名"], ["S001", None, "合成学生01"]]), "xlsx")
        self.assertEqual(preview(table, "roster", {"student_id": 0, "name": 2}).rows[0].action, "add")

    def test_xlsx_multiple_sheets_require_selection(self):
        payload = workbook(sheets=2)
        with self.assertRaises(ValueError):
            load(payload, "xlsx")
        self.assertEqual(load(payload, "xlsx", sheet="Sheet2").sheet, "Sheet2")
        with self.assertRaises(ValueError):
            load(payload, "xlsx", sheet="missing")

    def test_xlsx_cached_formula_never_becomes_candidate(self):
        table = load(workbook(formula=True), "xlsx")
        result = preview(table, "roster", {"student_id": 0, "name": 1})
        self.assertEqual(result.rows[0].action, "invalid")
        self.assertIn("name:formula_refused", result.rows[0].errors)

    def test_xlsx_unsafe_paths_external_links_macros_entities_and_expansion(self):
        for extra in ({"../escape": "bad"}, {"xl/vbaProject.bin": "bad"},
                      {"xl/externalLinks/link.xml": "bad"},
                      {"xl/danger.rels": '<Relationships><Relationship TargetMode="External" Target="fake"/></Relationships>'},
                      {"xl/danger.rels": '<!DOCTYPE x [<!ENTITY a "bad">]><x>&a;</x>'},
                      {"xl/danger.rels": '<!DOCTYPE x [<!ENTITY a "bad">]><x>&a;</x>'.encode("utf-16")},
                      {"large.xml": "x" * 500_000}):
            with self.subTest(paths=list(extra)), self.assertRaises(ValueError):
                load(workbook(extra=extra), "xlsx")

    def test_csv_limits_and_malformed_quoting(self):
        for payload in (b"x" * 2_000_001, b"a\n" * 2001, ("," * 30).encode(), b'"unclosed'):
            with self.assertRaises(ValueError):
                load(payload, "csv")

    def test_preview_is_deterministic_and_does_not_mutate_roster(self):
        known = {"S001": "old"}
        payload = "学号,姓名\nS001,合成学生01".encode()
        self.assertEqual(self.roster(payload, roster=known), self.roster(payload, roster=known))
        self.assertEqual(known, {"S001": "old"})

    def test_real_cli_reads_file_and_returns_typed_review_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.csv"
            path.write_text("学号,姓名\nS001,合成学生01", encoding="utf-8")
            before = path.read_bytes()
            result = subprocess.run([sys.executable, "-X", "utf8", "cli.py", str(path), "--profile", "roster"],
                                    cwd=Path(__file__).parent, capture_output=True, text=True, encoding="utf-8", check=True)
            self.assertEqual(json.loads(result.stdout)["rows"][0]["candidate"]["student_id"], "S001")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
