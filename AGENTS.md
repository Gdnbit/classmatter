# ClassMatter repository guide

## Authority and invariants

`docs/specs/class-os-v1/` and `.ai/gates/` are canonical product/release definitions. Web mock state is not business authority. The backend is a layered modular monolith, with separate Web/API processes. Authorized reads use Query Gateway; persistent business changes use Business Command Gateway; identity lifecycle uses Identity Security Boundary. AI output is a draft/candidate, not authorization. Agent, Capture, Memory and Knowledge cannot bypass those boundaries.

Synthetic development is admitted by `.ai/development/synthetic-policy.yaml` and its technical policy record. Formal release, real data and role signatures remain pending and must not be silently promoted. Use `python scripts/verify_synthetic_development.py --task <canonical-task-id>`. No Agent business-write tool, production credential or real student data is allowed.

## Work and verification

Plan before multi-file work. Map changes to requirements/evals/tasks, preserve task scopes and dependencies, reuse existing contracts, and keep diffs reviewable. Run the relevant `scripts/verify.ps1` suites and update documentation when status changes. Keep legacy protocol/import/environment/migration names stable; see the naming matrix. Do not rewrite migration history or Gate hashes.

`apps/web/` owns presentation and typed API clients; `backend/` owns domain/application/adapters; `contracts/` owns wire schemas; `scripts/` owns verification; `evals/` and `.ai/gates/` own executable intent and formal admission. No production database or uploads belong in Git.

Publication is default-deny. New or changed content needs review and explicit manifest refresh; run `scripts/public_guard.py` and the pinned secret scan. Do not place private reports, interviews, screenshots, runtime artifacts or identity maps in this tree. The owner selected Apache-2.0 and Gdnbit attribution; do not change those terms or perform a public push without a new explicit decision.
