# Synthetic deterministic grade analytics

Task02 (`contributor-tasks/02-grade-analytics.md`, proposed task-board branch)
was TODO/unassigned. Baseline main `61966bb`. Source audit found grade product
requirements and future pages, not a backend grade statistics service. This
isolated standard-library implementation addresses FR-GRD-001..005 calculation
and provenance concerns without promoting them into formal R1 applicability.

## Run

Python3.13.12 and PowerShell7, no new dependency:

```powershell
pwsh -NoProfile -File spikes/grade-analytics/run.ps1
python spikes/grade-analytics/cli.py --demo
python spikes/grade-analytics/cli.py --file synthetic-exams.json --student S001
```

JSON input is an array of1..20 exams. Each exam has exactly `exam_id`, `scope`
(`workspace`, `classroom`, `term`), `on` (ISO date), `subjects`, `students`, `marks`.
A subject is `{"subject_id":"math","maximum":"100"}`. A mark is
`{"student":"S001","subject":"math","raw":"80","source":{"batch":"B1","row":2,"version":1}}`.
Students is an array of stable synthetic IDs. Every entered mark requires source
batch/row/version. Duplicate JSON keys, student/subject cells, unknown objects,
contradictory raw/score/state and malformed metadata fail. JSON is at most2MB;
exam roster at most2000, subjects20, raw score128 characters. IDs are not names.

## Versioned calculation contract: synthetic-grade.v1

- Scores are finite Decimal, nonnegative, within declared subject maximum and
  at most4 fractional places. Zero is a real score. Maximum is positive and at
  most100000. `缺考`/`免考`/blank are absent/excused/not_entered, independently
  counted. Nonfinite, negative, out-of-range, excessive precision and nonnumeric
  values stay invalid, with raw input and provenance. They are never zero-filled.
- Student valid_total and valid_mean cover valid marks only and explicitly show
  valid_count. Complete_total and total rank exist only if every configured
  subject is valid; partial totals cannot enter the complete-score leaderboard.
  Subject means/ranks use only that subject's valid sample and show all states.
  Class complete_total_mean uses only complete students and shows complete_count.
- Display means use two decimal places, ROUND_HALF_UP. Ranks compare original
  unrounded exact totals/scores; competition ties are1,1,3. ID order makes tied
  presentation deterministic. Empty samples yield null, never NaN or fake zero.
- Comparisons require identical workspace/class/term and subject maxima, distinct
  exam IDs and increasing dates. Changed subjects/scales/scopes refuse comparison.
  Total differences and rank changes use the COMMON COMPLETE cohort, recomputing
  both ranks on that same group. Each exclusion and both roster sizes are shown;
  rank_gain is before paired rank minus after paired rank. Sources remain linked.
- Numeric sequence summaries require at least3 ordered compatible complete exams;
  missing middle data is not silently dropped. Output says increasing/decreasing/
  unchanged/mixed numerical sequence, with exact totals, exam IDs, sample count
  and original source refs. This is not a statistical/predictive student label,
  proof of sustained development or automated concern/action. No subject-imbalance
  inference is made without an independently approved rule.

The demo executes these rules on synthetic data, not hardcoded computed results.
The CLI emits all analyses, first/last comparison and the selected ID's numeric
sequence, with decimal/date values encoded as strings and nulls preserved.

## Boundaries, rollback and public content review

No DB, API, correction ledger, product UI, formal permission, R1/Gate/hash change,
business command or model/network call. Scope is fixture context, not real QG
authorization. No persistent grades are created or edited; a correction is a new
input snapshot and must be reanalyzed. Formal correction audit, user sample
adapters and production authorization remain outside this isolated task.

All new source/tests/demo metadata are first-party synthetic content. No actual
student data, credential, document, interview, model output or copied source.
The separate pinned read-only Windows/Ubuntu workflow supplements the untouched
full CI. Only explicit reviewed new paths enter PUBLIC_MANIFEST; existing hashes
and security exceptions are preserved. Actual runner/repository82-test/metadata/
fixture/docs/public-guard/pinned-secret-scan results are recorded in the PR;
remote module CI is not the full product baseline. Revert this directory, workflow
and its publication entries to roll back. Maintainer acceptance/merge is required
for DONE; no formal task/eval has been marked complete.
