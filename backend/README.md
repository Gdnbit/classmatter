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

The opt-in `conversation-d1` development schema now targets0025 with32 fixed tables; default R1 remains0016/22. `ConversationExitBusinessGateway` reuses ISB, recent human authentication, preview/approval, idempotent receipt and transactional audit. Its QG emits bounded v5 artifacts covering8 core,5 conversation/control and5 fixed recovery collections. There is no registered HTTP/UI/Agent export, admission or durable-input command and no implicit upgrade of existing instances. Historical formats below remain exact offline validators, not live migration heads.

For an already obtained synthetic artifact, the offline operator selects its exact profile:

```powershell
uv run --frozen python verify_exit.py '<download.json>' --profile conversation-v2
uv run --frozen python verify_exit.py '<original.json>' --profile conversation-v2 --compare-with '<copied.json>'
uv run --frozen python verify_exit.py '<new-v3.json>' --profile conversation-v3
```

Default `core-v1` behavior is unchanged. V2 rejects invalid relations, extra/unknown fields, orphan clear markers, visible cleared bodies, duplicate keys, oversized input and `--require-complete`; formatting-only copy changes return2. It never connects to a database or imports/activates data. Runs are source evidence only, not dispatch authority; AI replies remain unverified, not facts. Checksums do not authenticate the sender or prove current restrictions. The old formats do not authorize new-identity import; complete admitted recovery remains unimplemented. The isolated staging composition below is separate from offline validation.

V2 offline validation remains unchanged and is tested with a genuine old-format file. V3 has its own exact schema/revision, projects only the original fields through the unchanged v2 validator, and rejects non-null transfer metadata: a frozen source cannot emit another ordinary exit. A0020 source requires a new v3 export; old v2 artifacts are not silently promoted. Owned D1 checkpoints remain exact-head bound, so old0019 checkpoints require their compatible isolated verifier rather than automatic upgrade/activation.

The explicit0021 development profile emits `classmatter.synthetic-exit.v4`, adding exactly three closed recovery/provenance collections. Select `--profile conversation-v4` to verify these files; old v2/v3 validators are not widened. V4 independently validates and retains the complete audit set, including denied source-proof observations, without losing them in its private legacy projection. Native0021 files carry empty recovery collections. Imported pending snapshots retain original-author provenance and source audit evidence rather than relabeling the restorer as original author. Checkpoints include all30 registered tables and verify this provenance before accepting a snapshot; they still never activate it. Earlier exact-head checkpoints are not implicitly upgraded.

QG download refuses old artifacts after a clear or when restriction evidence is missing, corrupt or pending; clearing does not physically erase previously downloaded copies or old artifact bytes. The source artifact expires after30 minutes. Explicitly migrated D1 databases cannot be downgraded by reverting code: disable the development profile or forward-fix while preserving restriction evidence. This does not modify formal release admission or grant Agent business writes.

## Source-transfer freeze (synthetic composition only)

`SourceTransferGateway` registers one closed human command, `conversation.transfer.seal`, in the opt-in development profile only. It reuses recent authentication, Risk.X preview/approval, idempotent receipts and transactional audit. It verifies a current unexpired export against the current business snapshot and rejects active runs and self-target coordinates. Target coordinates are only a binding, not proof that a target exists or is authorized; target ISB/empty-store admission is subsequent work.

The fixed protected `conversation-transfer.dpapi` metadata file is published first, without overwrite. Only then are the SQL control marker, receipt and audit committed together. Any file evidence or SQL marker freezes ordinary D1 QG/BCG reads/writes, exports and body/context access. The narrowly scoped source command/status paths may finish or query the same attempt; normal Gateways cannot borrow this exception. A mislabeled default-R1 connection is rejected using the actual database revision, and the D1 restriction root must match the existing SQL authority before its apparent absence of a transfer file is trusted.

SQL/audit failure retains the file and freezes the source; a valid same-attempt retry may finish. There is no automatic thaw, timeout-based reset, target import/admission, source retirement or cross-host proof in this unit. A retry still needs the original artifact within its30-minute expiry and a valid approval/session; after expiry it remains frozen pending a future controlled diagnostic/forward-fix protocol. A hard exit after initial link publication can leave a temporary second hard link: evidence is retained and reads refuse, not auto-repaired. Source code rollback must not delete evidence or destructively downgrade0020. This is not a physical-erasure or whole-host rollback guarantee. No CLI/HTTP/UI/Agent route or existing-instance migration enables this command.

## Isolated target import (pending, synthetic composition only)

`TargetImportGateway` stages one closed human command after recent authentication and Risk.X approval. Its immutable1MiB native candidate must match a live, authorized `SourceTransferQueryGateway.committed_source` observation, the committed source receipt, source restriction head and exact target Owner/workspace/root binding. This QG operation releases metadata only, not source bodies, old approvals or offline authority. Reading a committed freeze does not renew an export download or turn a copied proof into a capability.

The target must have a freshly initialized control and no business entities/model configuration/export. Expanded v4 projection size and relations are checked before the fixed protected target-pending file is published. Typed entity/provenance/source-audit INSERTs, local restriction anchor, receipt and trusted local audit then commit atomically. A late verification or audit fault rolls back all SQL while retaining external isolation/clear evidence; only the same authorized attempt can retry. Cross-thread child identities keep their actual composite keys. Terminal runs are preserved, never reset or dispatched. Source audit rows are evidence in a separate table, not trusted target `business_audit`.

Local Owner FKs identify the actor who performed the import; the fixed batch and exact per-entity/version hashes preserve the original source author. They must not be presented as the same person. Ordinary QG/BCG/body/context/export access stays blocked while pending, including after process restart or lost/corrupt evidence. Final author-aware QG projections, mutable-provenance validation and target admission are still required before use; cross-host verification and multi-hop import are not implemented. No HTTP/CLI/UI/Agent path or user-instance migration enables staging. Do not delete evidence or destructively downgrade to thaw a target; preserve both sides and forward-fix or disable the unused profile.

## Committed target observation and source retirement (development only)

The target QG verifies its actual protected pending file, committed import receipt and current complete v4 snapshot before returning closed metadata. It returns no message bodies or transferable authorization. A trusted same-host `AuthorizedTargetReader` retains credentials only in memory and invokes that live QG; dictionaries and offline files are not substitutes.

`SourceRetirementGateway` requires current source ISB identity, authentication within5 minutes, Risk.X preview and human approval. It matches the source's committed seal to the exact target/Owner/root/package/receipt and pending snapshot. A fixed root-bound `conversation-retirement.dpapi` witness is published first; the existing BCG commits proposal/receipt/trusted audit together. No new SQL table, writer, role grant or Agent tool is introduced. SQL/audit failure preserves the file and isolation; same-attempt retry may finish. Once committed, a fresh proposal cannot create a second retirement; lost replies replay the original receipt. Retirement status requires both the current protected witness and its committed source seal/proposal/receipt. File-only evidence is not committed retirement.

Any retirement evidence also blocks resealing a different handoff after partial SQL/seal-file rollback and revokes the old source-staging proof. Only the private retirement retry/proof path may verify the old seal; there is no caller/Agent flag to bypass retirement. Missing/corrupt/foreign evidence never grants target admission, and neither timeout nor deleting a file thaws ordinary source operations. Existing5-second database lock/statement timeouts bound peer-lock conflicts; an already committed target rejects a new import preview before reentering its source. This is not a distributed transaction or a claim of no deadlocks.

Historical revision0022 only extended closed human command/risk constraints, leaving its30 tables unchanged. V4's `source_revision=0021` identifies its fixed projection baseline, **not** migration/ACL authority. Current live Stores independently require0025; old v2/v3/v4 offline validators remain unchanged. V5 retains its fixed0023 projection baseline, not a live-head authorization. SQL-only checkpoints do not contain external witnesses or authorize activation. Whole-host rollback, physical erasure and cross-host handoff are not proven. No user runtime has been migrated.

## Human target admission and editable origins (synthetic composition only)

After actual committed source retirement, `AdmissionGateway` uses recent human authentication, Risk.X preview/approval and the existing BCG to admit exactly the staged attempt. A live source retirement QG must match the current target stage. The fixed root-bound `conversation-admission.dpapi` witness is published first; the original proposal, receipt, trusted commit audit and two fixed append-only tables commit together. SQL/audit failure leaves isolation evidence and permits only a valid same-attempt retry. Missing/corrupt files, wrong root/Owner, missing original commit audit or altered origins deny ordinary access. Runtime has SELECT/INSERT only on the two new tables, no DDL or UPDATE/DELETE.

The target committed-stage QG preflights admission capacity before source retirement, including maximum timestamp width and the PG JSONB row budget; it publishes no simulated admission authority. Current v5 binds the complete fixed import batch, original source-audit set and per-entity/version origin registry by hashes. Original immutable identities, record revisions, turns and terminal runs cannot change. Versioned native edits retain original creation provenance; new record revisions belong to the actual local Owner. Identifier validity may close under existing BCG rules. Clear requires the existing external marker and NULL bodies; origins store body hashes, never baseline body copies.

`AdmissionQueryGateway` must use the actual `AdmissionTransaction`: its activity/history results explicitly distinguish original source author, local last editor and unverified assistant content. Old unqualified body readers and misassembled Gateways are denied; creating a source Owner account or calling imported local FK `created_by` the original author is forbidden. V5 exports intentionally include complete fixed origin metadata: consumers must resolve it rather than display restorer FKs as original authors. The private legacy validation projection is never emitted as an author-less imported artifact. Native local Roster/context retain their established DTOs without inventing authors. After committed admission the target can work without a live source session; initial admission cannot use a copied dictionary or offline file instead of the live proof.

Actual synthetic tests cover native rename/record correction/task update, author-aware QG, clear, PostgreSQL restart, checkpoint/pg_restore and v5 verification. Offline validation/checkpoint always reports `activation_allowed=false`; online same-host admission is a distinct human-authorized protocol, not `verify_exit` activation. Multi-hop is rejected before resealing. Disable an unused profile or forward-fix while preserving all witnesses; never delete evidence, auto-thaw, or destructively downgrade0023. Durable send/SDK/UI, editable work-summary generation, cross-host recovery, real Provider quality and teacher net-burden validation remain outstanding.

## Contracts and authority

### Durable human input (development composition, no dispatch)

`ConversationInteractionGateway` reuses the existing BCG/ISB transaction, metadata proposal, idempotent receipt and trusted audit. Explicit human create/rename methods bind a validated title only during that call; proposals contain `title_hash`, never the title. Human enqueue similarly persists the exact input only in the controlled user-message column, while its proposal records closed request metadata/hash. No universal candidate cache or Memory store is added. A committed queued receipt means input saved, **not** a Provider call or completed model response.

The fixed SQL implementation is mixed into the existing exact `AdmissionTransaction`, not a new database writer. Current class/term, original enrollment eligibility, restrictions and import/admission quarantine are checked. Concurrent same-key/same-input requests return the original run; differing input/mode/scope is rejected. Replays verify actual stored input and original proposal/receipt hash/version/kind/purpose/commit audit, not just a declared hash. Historical creation receipts remain valid after a legitimate rename. Archive is not delete and cannot hide an active run; clear cancels queued input and leaves no plaintext title/input copy in proposals.

QG returns an explicitly bounded latest50 list with a truncation flag, attributed visible history and metadata-only turn status without a generation/dispatch capability. This is not full history pagination or HTTP/UI binding. Native and admitted-target synthetic tests cover queue/clear/rollback/reopen/v5 and actual checkpoint clone verification. Historical revision0024 added four closed human W1 command types;32 tables and role column access remain unchanged. No Agent tool can invoke these human operations. Preserve all data/witnesses; disable unused profile or forward-fix rather than destructively downgrade.

### Durable run lifecycle and original SDK (opt-in server composition)

`ConversationWorkerGateway` adds four closed server operations inside the same BCG/ISB/receipt/audit transaction. Claim checks actual saved input and original enqueue evidence, then CASes queued version1 to running version2 with a fresh generation/one-minute lease. Only after commit does it return one process-local dispatch value; repeated/lost-reply claims never reissue it. Finish revalidates actual input, original claim canonical payload/hash/receipt/audit, scope/version/generation/lease. Output is only an assistant-unverified message; proposals contain hashes and bounded nullable metrics, never response text. Unknown tokens stay NULL, not fake zeroes. Cancel after dispatch is a request, not supplier cancellation; expired queued runs cancel and running runs become interrupted, never reset/retry automatically. Explicit0025 extends only four W1 constraints, retaining32 tables/existing ACLs and v5/checkpoint semantics.

`DurableChatRuntime` reuses the original Pydantic AI loop/model context/limits, without passing the BCG to the SDK. Only plain class-level chat is composed, rebuilding bounded visible history as untrusted text, never raw SDK/session/tool dumps. Final answer/completion wait for BCG persistence/audit and current QG visibility before each release. Clear-after-commit suppresses known stale output; this is not revocation of delivered text or an atomic UI guarantee. Disconnect/timeout/uncertain finalization are not false success or automatic paid retries; authorized lease reconciliation may still be needed. Temporary SDK history is discarded per run. Unknown outcome never proves zero Provider cost.

No HTTP/UI activation or user-instance migration. Structured historical query sources/draft cards, UI generation/clear fences, pagination and sourced work-summary remain subsequent required slices. Tests use offline FunctionModel, not real Provider quality/fee authorization. Teacher maintenance adds no step in this server-only slice; actual net-burden benefit remains unvalidated.

`src/class_os/domain` holds closed business rules; `application` owns QG/BCG/ISB; infrastructure adapters implement SQL/model/secrets; HTTP interfaces own strict wire DTOs and composition. `uv run --frozen python export_contracts.py --check` rejects contract drift. All business changes require validated command/preview/approval as applicable, idempotent receipt and transactional audit. Agent has no business-write or approval tool.

Default R1 migration head0016, 22 registered tables, risk r1.3; explicit D1 development head0025/32 is not R1 admission. Existing runtime instances have not been implicitly upgraded. No Agent/runtime DDL. Student IDs/references remain stable across display-name or term metadata correction. Permission, session, version or audit failure is fail-closed. Readiness/doctor/support are bounded diagnostics, not production certification or automatic repair.

## Verification and known limits

From the repository root, run `pwsh scripts/verify.ps1 -Suite backend` for non-DB tests; `-Suite db -PostgresRoot '<PG18目录>'` for disposable cluster and real browser regression; `-Suite all` includes other engineering suites. Tests allocate owned temporary clusters, never accept a shared DSN, and remove only their own synthetic fixtures.

Incomplete lifecycle/retirement, cross-host restore, representative teacher research and real-provider quality remain out of scope of a green synthetic build. Formal gates and security target binding remain pending. See [engineering overview](../docs/ENGINEERING_OVERVIEW.md) and [release scope](../docs/specs/class-os-v1/release-1-manifest.md).

## Optional synthetic desktop service

`desktop.py` is a fixed operator entry owned by the desktop supervisor, not an HTTP/Agent command runner. It only composes the existing synthetic runtime and serves the separate desktop R1 build. It does not initialize/migrate/bootstrap/start/stop PostgreSQL. The operator-only runtime directory argument supports isolated integration fixtures; no renderer can supply it. A per-process key and challenge/HMAC health proof bind the launched process; this is **not** user authorization, Domain Fact, admission or another business-write boundary. Normal QG/BCG/ISB checks remain unchanged.

The standalone development launcher and actual constraints are documented in [desktop README](../apps/desktop/README.md). `test_desktop_host.py` checks opt-in proof/invalid input and unchanged readiness/authorization; Windows `test_desktop_runtime.py` checks the real desktop against a disposable SCRAM cluster, including persistence and forced parent exit. Linux skips that Windows/DPAPI test explicitly; it is not evidence of Linux desktop support.
