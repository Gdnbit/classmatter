# ClassMatter public candidate audit

This is a safe summary, not private evidence or an anonymity guarantee. **Public open-source repository · Pre-alpha / synthetic-only; no GitHub Release and no real-student-data authorization.** The owner selected Apache-2.0/Gdnbit attribution and confirmed project/prototype redistribution rights.

Source was exported through a SHA-locked private allowlist into a clean history, then published to this independent GitHub repository. The first commit has no parents; the original source repository remains Private. Private research, source ledgers, images, archives, operational logs and databases are not transferred. Useful product conclusions are abstracted without quotations, interview dates or private source IDs. Explicitly synthetic demo labels replace unverified prototype name/school provenance.

Core source, contract/eval/test assets are retained. Machine Gate definitions, historical migrations and task row hashes are protected. Historical technical spike evidence is retained only for reproducibility; workstation/time metadata is omitted where not part of a drift contract. It is not evidence that the new candidate ran those historical experiments.

## Executed engineering verification

The final complete `verify.ps1 -Suite all` invocation returned **exit 0 in 924.642 seconds** on Windows with Python3.13.12, Node22.20.0, pnpm11.19.0, uv0.11.7 and PostgreSQL18.6. This is local evidence, not a remote CI run or production certification.

| Check | Result and scope |
|---|---|
| Repository/verifier negative tests | 81 passed, including public guard and exact checkout under `core.autocrlf=true` |
| Backend/contracts/non-DB | 278 passed; 313 database cases deselected, not counted as passed |
| Real disposable PostgreSQL/browser | 313 passed; 278 non-DB cases deselected; actual owner/class/roster/record/task/Today/timeline/preview/approval/audit flows |
| Additional nonempty upgrade regression | 1 passed separately after the complete run: existing 0015 business/identity rows and pending approval survive 0016; only the intended three column grants change, no schema CREATE permission |
| Web | 32 tests, typecheck and build passed; frozen install separately passed |
| Language spike | 3 Python +3 Node passed |
| Agent boundary spike | 68 Python +12 Node passed; fake/read/draft/stream/routing/SBOM checks, not real-provider quality |
| Self-host spike | 6 passed; historical live drill is not a fresh deployment test |
| Signature spike | 101 passed, 26 explicitly skipped; formal signatures/admission remain unapproved |
| Gates/fixtures/links | Original static checks passed; formal implemented-green count remains0 and authorization false |
| Secrets | Pinned Gitleaks8.30.1: 4 individually reviewed vector/SQL/synthetic-test matches, 0 unresolved; no directory ignore |
| Dependencies | Final Python audit found no known vulnerabilities; Web production audit found0. This is not all-platform/binary supply-chain certification |

Earlier CLI startup, test-injection and host-timeout failures are preserved privately rather than erased. The CLI now defers database/model imports for read-only diagnostics; its original time bounds and business tests remain. All original functional checks passed on the final rerun. See [dependency remediation](DEPENDENCY_REMEDIATION.md).

No unchecked platform artifact is included. The initial GitHub Actions [run 39148540124](https://github.com/Gdnbit/classmatter/actions/runs/39148540124) succeeded on the clean initial commit. The later published main-branch [run 39185506327](https://github.com/Gdnbit/classmatter/actions/runs/39185506327) also succeeded on commit `2abd45d` for Windows 2025 and Ubuntu 24.04; Ubuntu included disposable PostgreSQL/browser regression. The complete local Windows suite and formal release gates were not run remotely. The checked runs published no CI artifacts. The public manifest is default-deny and must not be refreshed automatically to hide failures. Raw transcripts, screenshots and private execution logs are not distributable reports. Final post-documentation scan/hash/export reproduction is recorded in restricted local QA; do not publish that raw evidence.

Legal third-party copyright notices may contain public upstream author names; they are not project user identities. Dependency licenses, binary notices and prototype rights are separate checks, not implied by a zero vulnerability count. Installed license metadata and exact upstream-tag supplements have been collected; this is not a binary-distribution clearance. See [third-party notices](../THIRD_PARTY_NOTICES.md).
