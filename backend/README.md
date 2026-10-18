# ClassMatter backend

Layered modular monolith, synthetic-only. Python 3.13, uv 0.11.7, PostgreSQL 18.6; Windows DPAPI is required for the persistent local entry point. The internal import/distribution remains `class_os` / `class-os-backend` for compatibility; no wire or persisted identifier migration is implied.

## Local entry point

Build `apps/web` first. From this directory:

```powershell
uv sync --frozen
uv run --frozen python local.py init --pg-root '<PostgreSQL18安装目录>'
uv run --frozen python local.py start
uv run --frozen python local.py bootstrap
uv run --frozen python local.py serve
```

Use <http://127.0.0.1:8000>. Keep generated passwords and recovery codes out of files/logs/Git. `init` does not overwrite a runtime; migrations must be explicit (`local.py migrate`), followed by rebuild/restart. `local.py stop` stops only the owned database. Do not copy `.local-runtime/` between hosts. `serve.py` is a health-only test entry and intentionally not ready; it is not the persistent composition.

## Contracts and authority

`src/class_os/domain` holds closed business rules; `application` owns QG/BCG/ISB; infrastructure adapters implement SQL/model/secrets; HTTP interfaces own strict wire DTOs and composition. `uv run --frozen python export_contracts.py --check` rejects contract drift. All business changes require validated command/preview/approval as applicable, idempotent receipt and transactional audit. Agent has no business-write or approval tool.

Current migration head0016, 22 registered tables, risk r1.3. Existing runtime instances have not been implicitly upgraded. No Agent/runtime DDL. Student IDs/references remain stable across display-name or term metadata correction. Permission, session, version or audit failure is fail-closed. Readiness/doctor/support are bounded diagnostics, not production certification or automatic repair.

## Verification and known limits

From the repository root, run `pwsh scripts/verify.ps1 -Suite backend` for non-DB tests; `-Suite db -PostgresRoot '<PG18目录>'` for disposable cluster and real browser regression; `-Suite all` includes other engineering suites. Tests allocate owned temporary clusters, never accept a shared DSN, and remove only their own synthetic fixtures.

Incomplete lifecycle/retirement, cross-host restore, representative teacher research and real-provider quality remain out of scope of a green synthetic build. Formal gates and security target binding remain pending. See [engineering overview](../docs/ENGINEERING_OVERVIEW.md) and [release scope](../docs/specs/class-os-v1/release-1-manifest.md).
