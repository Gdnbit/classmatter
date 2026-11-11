# Synthetic Excel/CSV import preview

Task01 (`contributor-tasks/01-import-workbench.md`, proposed task-board branch)
was TODO/unassigned. Baseline main `61966bb`. Audit: existing target-import code
is for controlled conversation recovery, not roster/exam spreadsheets; no roster
or exam file parser was found. FR-IMP-001/002/003/005 guide this isolated slice.
Formal import commits/compensation and R1 release applicability are excluded.

## Run

Python 3.13.12 / PowerShell 7, standard library only:

```powershell
pwsh -NoProfile -File spikes/import-workbench/run.ps1
python -X utf8 spikes/import-workbench/cli.py synthetic.csv --profile roster
python -X utf8 spikes/import-workbench/cli.py synthetic.xlsx --profile roster --sheet Sheet1
```

Create a synthetic CSV with headers `学号,姓名` and rows such as
`S001,合成学生01`. The CLI suggests only unique known headers. Use `--mapping`
with JSON zero-based column indices for explicit mapping, `--header-row` for a
nonfirst header, `--encoding gb18030` for explicitly selected legacy CSV encoding.
Grade profile headers are `学号,考试,科目,成绩`; pass `--roster` as a JSON ID/name
object so every grade matches a known synthetic ID. It never matches by name.
The library also accepts existing grade snapshots to show update/unchanged rows.

## Preview contract

Rows show add/update/unchanged/skipped/conflict/invalid with original source row,
file SHA-256, worksheet and exact mapping. Duplicate input IDs (or exam/subject/ID
keys) mark every participating row conflict, retaining other errors and releasing
no candidate. Mapped errors likewise release no candidate. Valid results are
frozen RosterCandidate or GradeCandidate values, never submitted commands.
Counts include every data record. Blank records are skipped; duplicate display
names with different IDs remain distinct. A changed known ID/name is an explicit
update preview, not silent identity merging. Source row for a multiline CSV
record means its starting physical line.

Grade values preserve zero, absent (`缺考`), excused (`免考`), not-entered (blank)
and invalid separately. Scores use finite Decimal, default range0..100; the
library requires an explicit maximum when another scale is used. This parser
does not perform grade aggregation or change formal records.

XLSX support is a bounded OOXML read subset: worksheet selection, inline/shared
strings, sparse coordinates and unformatted numeric/string cells. Multiple
worksheets require explicit selection. Formula cells are refused even with a
cached value. CSV formula-like mapped text is an error; there is no spreadsheet
export or formula execution. Dates/styles/merged cells/macros/legacy XLS are not
interpreted; unsupported mapped cell types become row errors. This is not a
general Excel compatibility claim. UTF-8 XML only; UTF-16 XML is refused.

Uploads are at most2MB; ZIP entries100, total inflated bytes8MB, compression
ratio200, table2000 rows/30 columns, cell4000 characters. DTD/entity declarations,
external links, macros, unsafe paths, duplicate ZIP entries and oversized content
are refused. Nothing is extracted to disk. Tests generate synthetic OOXML bytes
in memory; no binary fixture is published. No real user upload is included.

## Boundaries, verification and public review

This is an isolated CLI/library workbench, with header recognition, mapping,
validation and typed JSON review output. It does not add product UI, quarantine
storage, persistent mapping templates, API, DB, BCG/QG/ISB authority, migration,
dependency, release/Gate or frozen hash changes. The input bytes stay in memory;
the caller owns their real-world authorization. Preview data is not admission.
No commit endpoint exists. Revert this directory, its independent workflow and
publication entries to roll back; no database state needs restoration.

All new code, tests and fixtures are first-party synthetic content. No copied
source, identity, credential, private interview, actual document or paid call.
Only reviewed new paths are added to the exact-content public manifest; existing
entries and scanner exceptions stay unchanged. The standalone workflow reuses
existing pinned actions, Python3.13.12, read-only permissions and Windows/Ubuntu;
it supplements the original full CI without editing it. Local validation uses
this test runner, the repository82 verifier tests, metadata/development/fixture/
docs suites, public_guard and pinned scan_public --history. Actual results and
remaining upstream CI approval are recorded in the PR. Maintainer acceptance
and merge remain required before task DONE; production sample adapters and
general import commits are outside this task's authorized synthetic scope.
