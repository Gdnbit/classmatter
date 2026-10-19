# ClassMatter verification

`verify.ps1` is the existing engineering entry point. Use PowerShell 7, Python 3.13 and `pip install -r scripts/requirements-verify.txt`; Node/pnpm follow Web metadata. Backend/spikes use their own frozen uv lockfiles. Do not run all independent spike tests from a single bare pytest environment.

`self`, `eval-meta`, `gate-graph`, `task-graph`, `development`, `fixtures`, `docs`, `backend`, `web`, `db`, `language-spike`, `agent-spike`, `self-host-spike`, `signature-spike` can run independently. `all` runs engineering suites, not formal `security` target admission. The formal security runner is deliberately target-unavailable until a trusted adapter is bound; do not make it green with a fake target.

`db` uses a new owned disposable PostgreSQL cluster, not a shared DSN. Pass `-PostgresRoot` explicitly on a new machine. Linux CI executes its applicable subset; Windows DPAPI/Edge and local lifecycle tests need the supported host. A workflow file is not evidence of a successful remote run.

`public_guard.py` verifies reviewed paths and exact content hashes plus forbidden materials/PII patterns. Its manifest is not automatically refreshed by CI. `scan_public.py` scans an isolated copy of exactly those reviewed files with pinned Gitleaks; reports remain under ignored test-results. Exact test-vector false positives are reviewed per path/rule/content fingerprint, not whole-directory exclusions. `--require-license` adds the intentionally blocking owner-license check.

## CI change scopes

GitHub Actions runs once for each pull request and after changes reach `main` (no duplicate branch-push + PR runs). The always-on **Public content, secrets and docs** job checks the exact SHA-256 public allowlist, forbidden/identifying content patterns, pinned Gitleaks against the full public Git history, and Markdown UTF-8/local links. The safety checks cannot be skipped by classifying a change as documentation-only.

A narrow set of presentation files (`README.md`, `README_EN.md`, `CONTRIBUTING.md`, `BRAND_MIGRATION_MATRIX.md`, and selected overview/audit docs) can use this lighter path. A changed `PUBLIC_MANIFEST.json` is permitted only alongside one of those documents, and the manifest must explicitly record the new content hashes. A manifest-only change is **not** lightweight. Canonical specs, security policies, workflows, guard scripts, tests, source code, lockfiles, added binaries, unexpected paths and mixed changes all trigger both Windows/Ubuntu engineering jobs.

The change classifier fails closed: an unknown event, missing ancestry, shallow history, invalid Git SHA, force-push baseline or diff error triggers the full suite. Manual `workflow_dispatch` always runs full tests. These are engineering checks, not formal R1 acceptance, real-student-data admission, publication authorization or production readiness. See `scripts/ci_change_scope.py` and its regression tests.
