# Synthetic work runtime recovery experiment

Contributor task: `contributor-tasks/06-agent-work-runtime-spike.md` on the
proposed `docs/contributor-task-board` branch. Audited TODO/unassigned, with no
corresponding open PR. Product baseline: main `61966bb`. This independent spike
does not modify the task board, R1, D1 conversation worker or any business tool.

## Run

Python 3.13.12 and PowerShell 7, with the standard library only, from repo root:

```powershell
pwsh -NoProfile -File spikes/work-runtime/run.ps1
python spikes/work-runtime/demo.py
```

The demo enqueues a synthetic draft review, refuses execution without fake human
approval, records exactly one fake tool effect, injects a worker crash, replaces
the runtime object, recovers by receipt after lease expiry, and refuses duplicate
delivery. Neither command installs dependencies, opens network connections,
starts services or writes documents/databases (ordinary bytecode caches aside).

## Audit and smallest independent gap

| Area | Existing evidence | Increment here |
| --- | --- | --- |
| Server claim/cancel/reconcile | `backend/src/class_os/domain/conversation_worker.py`, `application/conversation_worker.py`, worker unit and actual PG gateway tests | Preserve these production paths; no parallel production worker |
| Durable conversation execution | D1 worker already verifies inputs, generations, leases, committed evidence and cancellation | Separate generic fake-work acceptance harness, with no conversation dispatch |
| Lost external reply/retry | Future research WK-05/06/07 asks for duplicate, crash and lost-receipt drills | A queryable idempotent fake receipt ledger, before/after-effect crash points and bounded retry |
| Waiting authorization | Future WK-08/09/10 and product research require fresh source/approval checks | Recheck scope, source revision, approval generation, expiry and revocation before dispatch, finish and recovery |

Related design: LR-WRK-001, LR-KRN-001, LR-DER-001 and the Future work/runtime
research. This does not implement or promote their formal release applicability,
all WK scenarios, Pi comparisons, model quality or teacher net-value research.

## State and evidence rules

`approval_wait` → `running` → `completed` requires a matching actual fake-tool
receipt, not an Agent statement or a caller-created expected receipt. Input,
scope, source revision, deadline and the fixed tool name bind the request hash.
Reusing the same scoped key with different input fails. The tool is exactly
`fake.review.v1`; there is no Shell, arbitrary URL, SQL or plugin interface.

Each claim issues a new generation and exclusive lease. Repeated claims or
dispatches cannot issue another active execution. Before calling the fake tool,
the dispatch intent and metadata event are recorded atomically by the fake
store. Failed claim/intent writes cannot release work to the tool. Old tickets,
expired leases and late completions are refused. A store-scoped fixture policy
prevents worker replacement from silently increasing retries or lease duration.

A known pre-effect failure goes to `retry_wait`, with exponential delay starting
at two seconds, capped at sixty seconds, and at most three attempts by default.
An uncertain reply goes to `unknown`; it is never directly claimable. After the
lease expires, recovery queries the authoritative fake ledger. A matching receipt
can finish; confirmed absence can schedule a retry; unavailable lookup leaves the
outcome unknown. Reconciliation checks wait sixty seconds between failures and
stop at the configured attempt limit in `blocked`. Repeated premature wakeups do
not append duplicate events or replay tools.

The fake ledger's absence result is a definitive no-effect proof ONLY because
this fixture is synchronous and in memory. An eventually consistent real service
cannot safely inherit this assumption. A receipt without a recorded dispatch
intent, altered receipt or changed source/permission/approval blocks completion.
Every completion/recovery also checks the current fake approval generation;
renewing approval cannot authorize an earlier ticket.

Cancellation is terminal. It prevents later completion or execution but cannot
undo a fake effect already recorded. Similarly, revoked/expired approval after
the effect leaves the work blocked, with no accepted completion receipt; the
tool ledger still contains the effect for inspection. Completed work is not
retroactively undone by a later cancel. No automatic unblocking or permissions
upgrade exists; failed work requires human inspection and a new request.

## Acceptance and limitations

The tests cover duplicate delivery, two workers concurrently claiming the same
fake store, crashes before/after the tool, lost receipt, lookup outage, bounded
retry, cancellation before/after the effect, source changes, approval expiry and
revocation, fake state/event failure, forged completion and policy substitution.

Recovery is a SIMULATION: the same `FakeStore`, `FakeAuthority` and `FakeTool`
objects survive replacement of a `Runtime` object. No OS process is killed; no
durable disk state, transactional database, distributed lease, network transport,
actual human login or actual approval authority is implemented. The lock proves
same-process fixture claim exclusivity, not distributed concurrency. Source and
approval fixture mutation is tested at explicit phase boundaries, not as an
atomic distributed authorization service. Supplied UTC time is trusted; clock
rollback is outside the model. Generation numbers and hashes are correlation,
not security capabilities. Fake component APIs are fixture setup, not public APIs.

No production QG/BCG/ISB, API, persistence, migration, Agent tool, model runtime,
paid call, Release/Gate, requirement hash or permission rule changes. Integrating
real state/tools requires a separately approved release and the existing trusted
gateways. This harness cannot prove actual process recovery or exactly-once real
side effects. Revert this directory, its workflow and publication entries to
roll back; there is no user instance or database to migrate or remove.

## Public content review and verification

All added implementation, tests, runner, demo and documentation are first-party
synthetic fixtures. No copied implementation, real identity, interview, user
record, source upload, screenshot, credential, model response or paid request is
included. Metadata events contain operation hash, state, attempts, reason and
time, without synthetic input text. Existing security/secret-scan exceptions,
formal manifests and default-deny guard behavior stay unchanged. Only reviewed
new paths receive exact SHA-256 publication entries.

The separate `work-runtime-spike.yml` workflow uses the repository's existing
SHA-pinned checkout/setup-python actions, Python 3.13.12, read-only contents
permission, no persisted checkout credentials, no secret references, a five-minute
budget and the Windows/Ubuntu matrix. It adds a source guard and this test suite;
it does not replace or edit the existing full baseline CI. Fork branch pushes can
run this isolated check; upstream PR workflows may require maintainer approval.
Task05's unmerged PR is not a dependency and its files are not imported here.

Local verification also uses `scripts/verify.ps1` suites docs/self/eval-meta/
gate-graph/task-graph/development/fixtures, the 82 verifier tests,
`python scripts/public_guard.py --require-license` and pinned
`python scripts/scan_public.py --history`. Their actual results belong in the PR,
not prefilled as release admission. Full product/DB/browser/Electron verification
is outside this isolated standard-library change and remains in baseline CI.
Only the maintainer may mark the task DONE after review and merge.
