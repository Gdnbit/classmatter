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

## Owned synthetic checkpoint discovery and checking

These trusted local operator commands use the existing runtime; they are not Agent tools or HTTP endpoints:

```powershell
uv run --frozen python local.py backup
uv run --frozen python local.py backup-list
uv run --frozen python local.py backup-check --backup-id '<UUID from backup-list>'
```

`backup-list` is read-only and works while PostgreSQL is stopped. It inspects only this runtime's owned directory, returns UUIDs, validated creation times and `metadata-verified`/`rejected`; it never returns filenames, credentials, row contents or raw failure messages. A metadata-verified checkpoint has **not** been restore-verified: run `backup-check` to restore into an isolated temporary database, compare registered-table hashes and validate schema/roles, then remove that clone. A failed check never switches or replaces the source. Rejected metadata can indicate corruption, a different runtime binding, a protected-file access problem or an incompatible head; it does not diagnose which one or delete the file. Pending/foreign files are reported only as counts and never imported.

Discovery rejects rather than returning a partial result above 128 directory entries or 64 MiB of candidate protected packets. Each packet retains the existing 32 MiB limit. File publication now syncs encrypted bytes in a temporary file before an atomic exclusive hard link; a collision never replaces an existing checkpoint. Filesystems lacking hard-link support reject creation without a fallback that could expose partial files. An abrupt process/host failure may leave a `.pending` file; discovery does not treat it as a checkpoint or silently delete it. No automated retention/deletion, cross-machine recovery, production backup, PITR or complete lifecycle/exit guarantee is provided. DPAPI and runtime binding remain unchanged; do not copy the runtime or its backups to another host.

The local NTFS and CI Linux filesystems support this hard-link publication. Atomic visibility is not a guarantee of power-loss durability: directory metadata is not separately fsynced, so a successful command is not evidence that a newly published filename survives a sudden host power loss. Preserve earlier checked checkpoints and verify again after an abnormal shutdown; no RPO/RTO promise is made.

For explicit D1 development composition, `SyntheticBackup.check_current_restrictions(backup_id, restrictions)` additionally compares the source database anchor and same-runtime protected file, validates the actual restored clone against those markers, then rechecks the source. Missing/corrupt/pending evidence, an old head, orphan markers or old visible rows behind a current anchor reject. The port must be the fixed `ProtectedConversationRestrictions` for this runtime; a supplied proof dictionary or foreign root is not accepted. The unchanged `check` method still tests snapshot integrity only, so an old structurally valid snapshot may pass `check` and fail this stronger check.

The stronger report explicitly returns `current_restrictions_verified_at_check=true`, `observation_only=true` and `activation_allowed=false`. It is an observation, not a lease, permanent recovery credential or imported-data authorization: restrictions can change immediately afterwards. No new CLI/HTTP/Agent route, database writes, target activation or existing-instance upgrade is registered. A future typed import must independently establish current-source/target authority at commit and handle cross-database failures. Whole-host rollback, physical erasure and portable/new-identity recovery are not proven by this check.

## Offline core exit transfer checks

An owner-approved core JSON download can be checked without a running database, login, model or network connection:

```powershell
uv run --frozen python verify_exit.py '<download.json>'
uv run --frozen python verify_exit.py '<original.json>' --compare-with '<copied.json>'
```

Both files must pass the same existing fixed-domain validator. The report includes SHA-256 of file bytes, canonical package and core checksums, plus separate `same_file_bytes`, `same_package` and `same_core` comparisons. Exit 0 means a valid core, and when comparing, an exact copy; exit 2 means both are valid but differ; exit 1 rejects invalid/incomplete input. Formatting-only changes can preserve canonical package/core hashes but are not an exact transfer. A newly generated export may preserve core data while changing package metadata or audit evidence; this is distinguished, not called a restore success. Outputs omit paths, identities and content. Only bounded regular local files are read; leaf symlinks/junctions, directories, special files, duplicate JSON fields, invalid constants and oversized packets are rejected.

No file or database is written, imported, initialized or switched. Checksums detect differences, not an authorized sender or forged but rehashed data; use a separately trusted source/digest when authenticating provenance. `--require-complete` still rejects this core-only profile. Tests copy a synthetic actual BCG/QG export into another local file and check no database changes; Windows/Ubuntu CI verifies the code on each platform, not a physical cross-machine restoration. Complete lifecycle, identity re-enrolment, cross-host import and retirement remain unimplemented.

## Explicit D1 versioned exit evidence (development only)

The opt-in `conversation-d1` schema now targets0020 with27 fixed tables; default R1 remains0016/22. `ConversationExitBusinessGateway` reuses ISB, recent human authentication, preview/approval, idempotent receipt and transactional audit. Its QG now emits a bounded v3 artifact covering8 core and5 conversation/control collections, including the3 new source-transfer control columns. There is no registered HTTP/UI/Agent export command and no implicit upgrade of existing instances.

For an already obtained synthetic artifact, the offline operator selects its exact profile:

```powershell
uv run --frozen python verify_exit.py '<download.json>' --profile conversation-v2
uv run --frozen python verify_exit.py '<original.json>' --profile conversation-v2 --compare-with '<copied.json>'
uv run --frozen python verify_exit.py '<new-v3.json>' --profile conversation-v3
```

Default `core-v1` behavior is unchanged. V2 rejects invalid relations, extra/unknown fields, orphan clear markers, visible cleared bodies, duplicate keys, oversized input and `--require-complete`; formatting-only copy changes return2. It never connects to a database or imports/activates data. Runs are source evidence only, not dispatch authority; AI replies remain unverified, not facts. Checksums do not authenticate the sender or prove current restrictions. Actual new-identity import, source freshness and complete recovery remain unimplemented.

V2 offline validation remains unchanged and is tested with a genuine old-format file. V3 has its own exact schema/revision, projects only the original fields through the unchanged v2 validator, and rejects non-null transfer metadata: a frozen source cannot emit another ordinary exit. A0020 source requires a new v3 export; old v2 artifacts are not silently promoted. Owned D1 checkpoints remain exact-head bound, so old0019 checkpoints require their compatible isolated verifier rather than automatic upgrade/activation.

QG download refuses old artifacts after a clear or when restriction evidence is missing, corrupt or pending; clearing does not physically erase previously downloaded copies or old artifact bytes. The source artifact expires after30 minutes. Explicitly migrated D1 databases cannot be downgraded by reverting code: disable the development profile or forward-fix while preserving restriction evidence. This does not modify formal release admission or grant Agent business writes.

## Source-transfer freeze (synthetic composition only)

`SourceTransferGateway` registers one closed human command, `conversation.transfer.seal`, in the opt-in development profile only. It reuses recent authentication, Risk.X preview/approval, idempotent receipts and transactional audit. It verifies a current unexpired export against the current business snapshot and rejects active runs and self-target coordinates. Target coordinates are only a binding, not proof that a target exists or is authorized; target ISB/empty-store admission is subsequent work.

The fixed protected `conversation-transfer.dpapi` metadata file is published first, without overwrite. Only then are the SQL control marker, receipt and audit committed together. Any file evidence or SQL marker freezes ordinary D1 QG/BCG reads/writes, exports and body/context access. The narrowly scoped source command/status paths may finish or query the same attempt; normal Gateways cannot borrow this exception. A mislabeled default-R1 connection is rejected using the actual database revision, and the D1 restriction root must match the existing SQL authority before its apparent absence of a transfer file is trusted.

SQL/audit failure retains the file and freezes the source; a valid same-attempt retry may finish. There is no automatic thaw, timeout-based reset, target import/admission, source retirement or cross-host proof in this unit. A retry still needs the original artifact within its30-minute expiry and a valid approval/session; after expiry it remains frozen pending a future controlled diagnostic/forward-fix protocol. A hard exit after initial link publication can leave a temporary second hard link: evidence is retained and reads refuse, not auto-repaired. Source code rollback must not delete evidence or destructively downgrade0020. This is not a physical-erasure or whole-host rollback guarantee. No CLI/HTTP/UI/Agent route or existing-instance migration enables this command.

## Contracts and authority

`src/class_os/domain` holds closed business rules; `application` owns QG/BCG/ISB; infrastructure adapters implement SQL/model/secrets; HTTP interfaces own strict wire DTOs and composition. `uv run --frozen python export_contracts.py --check` rejects contract drift. All business changes require validated command/preview/approval as applicable, idempotent receipt and transactional audit. Agent has no business-write or approval tool.

Current migration head0016, 22 registered tables, risk r1.3. Existing runtime instances have not been implicitly upgraded. No Agent/runtime DDL. Student IDs/references remain stable across display-name or term metadata correction. Permission, session, version or audit failure is fail-closed. Readiness/doctor/support are bounded diagnostics, not production certification or automatic repair.

## Verification and known limits

From the repository root, run `pwsh scripts/verify.ps1 -Suite backend` for non-DB tests; `-Suite db -PostgresRoot '<PG18目录>'` for disposable cluster and real browser regression; `-Suite all` includes other engineering suites. Tests allocate owned temporary clusters, never accept a shared DSN, and remove only their own synthetic fixtures.

Incomplete lifecycle/retirement, cross-host restore, representative teacher research and real-provider quality remain out of scope of a green synthetic build. Formal gates and security target binding remain pending. See [engineering overview](../docs/ENGINEERING_OVERVIEW.md) and [release scope](../docs/specs/class-os-v1/release-1-manifest.md).

## Optional synthetic desktop service

`desktop.py` is a fixed operator entry owned by the desktop supervisor, not an HTTP/Agent command runner. It only composes the existing synthetic runtime and serves the separate desktop R1 build. It does not initialize/migrate/bootstrap/start/stop PostgreSQL. The operator-only runtime directory argument supports isolated integration fixtures; no renderer can supply it. A per-process key and challenge/HMAC health proof bind the launched process; this is **not** user authorization, Domain Fact, admission or another business-write boundary. Normal QG/BCG/ISB checks remain unchanged.

The standalone development launcher and actual constraints are documented in [desktop README](../apps/desktop/README.md). `test_desktop_host.py` checks opt-in proof/invalid input and unchanged readiness/authorization; Windows `test_desktop_runtime.py` checks the real desktop against a disposable SCRAM cluster, including persistence and forced parent exit. Linux skips that Windows/DPAPI test explicitly; it is not evidence of Linux desktop support.
