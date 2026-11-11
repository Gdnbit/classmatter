# Synthetic seating solver and manual preview

Task03 (`contributor-tasks/03-seating-planner.md`, proposed task board) was
TODO/unassigned. Baseline main `61966bb`. Existing `demo/seat-plan.ts` validates
only an explicit two-person exchange in the mock store; it is not a general
layout/constraint solver. This independent slice follows FR-SEA-001..004 without
registering a formal business writer, release or real-data feature.

## Run and use

Python3.13.12 / Node22 / PowerShell7. The application and solver use only standard
libraries; browser tests reuse the existing locked apps/web Playwright1.64.0.

```powershell
python spikes/seating-planner/serve.py
node --test spikes/seating-planner/solver.test.mjs
pwsh -NoProfile -File spikes/seating-planner/run.ps1
```

Open the loopback URL printed by serve.py (default port8766, `--port 0` chooses
an ephemeral port). Set layout, synthetic IDs, unavailable seats, fixed positions
and explicit nonadjacent pairs. Generate and compare up to3 candidate maps.
Select a student then an available target, using mouse or Enter/Space, or drag
the student to a target. An occupied target swaps the two students. Undo restores
the last accepted preview. Every manual operation rechecks all hard constraints;
an invalid move leaves the previous map unchanged and explains the conflict.

Current positions can be entered in the expandable baseline field; differences
show original and preview positions. Without a baseline, placement is marked as
new. Changing any setting clears all old candidates and manual controls. Refresh
clears state. There is no official application, save, upload or download action.

For browser tests, install apps/web with the existing frozen lockfile and its
Playwright Chromium. `SEATING_PYTHON` may select the interpreter; local supported
Edge can be selected with `SEATING_BROWSER_CHANNEL=msedge`. A provisioned runtime
can set `PLAYWRIGHT_TEST_MODULE` to an existing Playwright test module. These
overrides are test infrastructure only, never browser-delivered configuration.
Tests start/stop their own ephemeral loopback server and retain screenshots under
ignored test-results. No own-app response is mocked.

## Deterministic solver and boundaries

Adjacency is Manhattan distance1: horizontal/vertical, never diagonal. Layout is
at most48 seats with1..8 rows/columns; roster1..20 unique stable synthetic IDs.
Unavailable seats, fixed placements and explicit apart pairs are hard rules.
They cannot be offset by the changed-seat score. Unknown fields, prototype-property
IDs, malformed references, duplicates and invalid layouts are refused.

Bounded backtracking uses deterministic minimum-domain ordering. Candidate
ordering favors fewer differences from the original map; this is a transparent
soft score, not a global optimality guarantee. Default budget20000 nodes, at most
3 candidates (API bounds50000/5). Exhaustively incompatible constraints produce
an explained unsatisfiable result. Budget exhaustion without a solution produces
search_limited, not a false no-solution claim. Explanations identify a shortage,
fixed/blocked/pair conflict or an infeasible combination, not a minimal unsat core.

Plans bind the normalized configuration; stale or corrupted candidates cannot be
manually adjusted. Immutable assignments and differences prevent accidental
mutation of the previous preview. No score/health/behavior inference exists.
The static server serves only four named files on127.0.0.1, checks Host, denies
unknown paths/writes and sets a no-network CSP. It is a local test host, not a
production web/API or identity boundary. No product API/schema, migration, scope
permission, model, dependency, release/Gate/frozen hash or official assignment
changes. Revert this directory/workflow/publication entries; no user data to undo.

## Visual and public review

PRODUCT.md scopes this Operate surface. It inherits the existing app's system CJK
typography, #f6f7f4 ground, #182018 text and #1e5d50 primary. Desktop separates
conditions and classroom; mobile stacks them with an internally scrollable wide
canvas. Keyboard focus, pressed/disabled states, alerts, synthetic boundaries and
the before/after table are explicit. No new global visual system is introduced.

All source, UI copy and test fixtures are first-party and synthetic. No original
student document, credential, private source, model call, image or paid service.
Only explicit new paths enter PUBLIC_MANIFEST; original hashes and exceptions
stay unchanged. Separate read-only pinned Windows/Ubuntu CI reuses existing
locked Playwright tooling and supplements, rather than changes, full baseline CI.
Local checks include15 solver tests and9 real browser cases, repository82 tests,
metadata/development/fixtures/docs, public_guard and pinned scan_public --history.
The first browser run had2 failures locating multiline textarea labels; explicit
aria-labelledby fixed the actual accessible names, and unchanged scenario
assertions then passed. Exact command results and remote CI are recorded in PR.
Maintainer review/merge is required before DONE; no official task status changed.
