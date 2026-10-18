# ClassMatter verification

`verify.ps1` is the existing engineering entry point. Use PowerShell 7, Python 3.13 and `pip install -r scripts/requirements-verify.txt`; Node/pnpm follow Web metadata. Backend/spikes use their own frozen uv lockfiles. Do not run all independent spike tests from a single bare pytest environment.

`self`, `eval-meta`, `gate-graph`, `task-graph`, `development`, `fixtures`, `docs`, `backend`, `web`, `db`, `language-spike`, `agent-spike`, `self-host-spike`, `signature-spike` can run independently. `all` runs engineering suites, not formal `security` target admission. The formal security runner is deliberately target-unavailable until a trusted adapter is bound; do not make it green with a fake target.

`db` uses a new owned disposable PostgreSQL cluster, not a shared DSN. Pass `-PostgresRoot` explicitly on a new machine. Linux CI executes its applicable subset; Windows DPAPI/Edge and local lifecycle tests need the supported host. A workflow file is not evidence of a successful remote run.

`public_guard.py` verifies reviewed paths and exact content hashes plus forbidden materials/PII patterns. Its manifest is not automatically refreshed by CI. `scan_public.py` scans an isolated copy of exactly those reviewed files with pinned Gitleaks; reports remain under ignored test-results. Exact test-vector false positives are reviewed per path/rule/content fingerprint, not whole-directory exclusions. `--require-license` adds the intentionally blocking owner-license check.
