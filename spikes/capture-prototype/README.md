# Source-bound synthetic Capture and human review

Task04 (`contributor-tasks/04-capture-prototype.md`, proposed task board) was
TODO/unassigned. Baseline main `61966bb`. Existing agent verbatim quote/span and
SDK ResultCapture already bind a current turn's source/task result; they are not
a general file source lifecycle or name-resolution workbench. This spike adds
only that isolated gap, preserving the existing SDK and production boundaries.
LR-CAP-001/LR-RES-001/LR-EPI-001/LR-DER-001 and T-EVO-002 inform the design, not a
formal applicability change or claim that their complete contracts are shipped.

## Run and perform human review

Python3.13.12 / PowerShell7, standard library only:

```powershell
pwsh -NoProfile -File spikes/capture-prototype/run.ps1
python -X utf8 spikes/capture-prototype/cli.py synthetic.txt --roster '{"S001":"同名合成","S002":"同名合成"}'
python -X utf8 spikes/capture-prototype/cli.py synthetic.txt --roster '{"S001":"同名合成","S002":"同名合成"}' --review
```

Create a synthetic UTF-8 .txt file using the exact transparent line grammar:

```text
同名合成 | note | 合成资料待核对
id:S001 | task | 核对合成清单
```

Default mode prints typed JSON drafts/issues only. `--review` prints the literal
content and candidate IDs, then asks for one explicit ID to accept as a candidate,
`r` to reject or `q`/EOF to stop. Even a uniquely matched ID is never autoaccepted.
The file byte digest is rechecked after each actual human input; a changed file
aborts and requires recapture. Tests exercise real subprocess stdin interaction
and a file edit during that waiting interval. No output or database file is saved.

The library accepts in-memory synthetic Source/Roster fixtures and exposes the
same preview/review protocol. A formal UI/Channel/BCG is deliberately absent.

## Provenance, matching and invalidation

- A source binds workspace/class/term/owner/purpose, stable ID, monotonic version,
  validity and decoded UTF-8 text SHA-256. Blank input, expired/withdrawn/missing
  sources and version replay fail. Withdrawn data cannot be revived by replaying
  its original version. Reinstatement requires a new explicit revision.
- Draft refs identify source version/hash, physical line and Python Unicode
  code-point [start,end) in the original decoded source. Quote is preserved
  exactly, including spaces; CRLF/emoji/blank-line tests verify offsets. The
  reference digest covers decoded source text; CLI additionally checks original
  file bytes (including BOM) during human review.
- ID matching and NFC-exact name matching produce a sorted candidate set. Same
  names remain ambiguous. Unprefixed ID/name collisions also stay ambiguous;
  `id:` and `name:` explicitly choose the identifier namespace. Unknown mentions
  remain unmatched; no new student or guessed identity is created.
- The roster version AND full sorted ID/name snapshot digest bind each draft.
  Source/roster edits, withdrawal or expiry invalidate all older drafts and
  reviewed candidates before reuse. Reconstructing the draft from current input
  rejects text/locator/candidate substitutions. Candidate lookup releases no
  object after invalidation. Previously returned text in caller memory cannot
  be forcibly retracted; callers must revalidate before reuse.
- Human selection must belong to the current candidate set. Output state is
  reviewed_candidate_not_committed. Review records are process-local fixture
  evidence, not identity authentication, official approval or a business Command.
  Rejected selections never release a candidate. There is no fact writer.

Only note (max1000 characters) and task (max80 characters) draft kinds exist.
Unknown kinds, unstructured lines and empty/oversized fields produce located
issues, not inferred facts. Input instruction-like text remains literal quoted
data. No model, eval, shell, URL, SQL, tool dispatcher or approval parser exists.
This limited grammar's injection tests are not a claim of model robustness.

## Bounds and excluded capabilities

UTF-8 .txt only, at most200KB original bytes,64000 decoded characters,500 source
lines,100 drafts and2000 unique roster IDs. NFC matching does not implement fuzzy
aliases, pronouns, date/type inference, OCR/ASR, PDFs, office documents or free-text
language understanding. Split oversized synthetic sources explicitly; no silent
truncation. Scope is supplied fixture context, not QG/ISB authorization. Source
and review stores survive only within the current process and are not BCG-backed
persistence; clock is trusted UTC and concurrent distributed source mutation is
outside this harness. Production integration requires a separately approved
release and the existing gateways. Do not use real students or private files.

No product API/DB/schema/migration, production dependency/permission, formal
Release/Gate/hash or security exception change. Revert this directory, workflow
and reviewed publication entries to roll back; there is no user state to migrate.

## Public source review and validation

All implementation, CLI, tests and text fixtures are first-party and synthetic;
no copied source, private document, interview, actual identity, credential, model
response or paid request is included. Only explicit new paths are added to the
exact-content manifest; all original entries/exceptions remain. Separate pinned
read-only Windows/Ubuntu CI supplements the untouched full baseline workflow.
Validation includes source lifecycle, all5 scope dimensions, name/ID ambiguity,
tampering, injection-as-data, Unicode spans, real CLI review and stale-file
rejection; plus repository82 tests, metadata/development/fixtures/docs, public
guard and pinned file/history scan. Actual commands/results and any upstream CI
action_required are recorded in PR; only maintainer acceptance/merge can set DONE.
