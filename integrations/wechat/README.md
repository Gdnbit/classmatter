# Personal WeChat connector workbench

2026-11-01: four executable adapter implementations, isolated workers and a separate native workbench. Engineering candidate, not a released R1 feature. The existing application does not yet have an admitted Capture store or Agent WeChat tool. No live SDK/client pairing has been accepted. No account-ban probability is asserted.

## Teacher value and limits

Read a chosen conversation once, keep a resumable local candidate, inspect source and coverage, and optionally prepare one explicit reply. Teachers should not retype available messages. This laboratory does not determine responsibility, infer student facts, send automatic replies, continuously scan every group, or duplicate messages into the business database.

| Preset | Integrated operations | Historical coverage | Activation and outstanding condition |
| --- | --- | --- | --- |
| usechat | Visible-window read; single text submission | Current visible messages; no invented scroll/backfill API | Explicit operator model authorization, installed CLI/native Helper, client smoke |
| pyweixin | pull_messages; single text submission | Requested UI history, capped at 500 per invocation; short result never proves end | Visible UIA tree, isolated Python and inspected source, client smoke |
| replica | get_messages pagination; restart/resume | Accessible local message shards for an exact native conversation ID | Explicit local account directory, optional SDK; no GUI/send activation in this adapter |
| wxautox4 | ChatWith/ChatInfo/GetAllMessage/SendMsg | Current window; no invented full-history API | Vendor activation/commercial terms, isolated Python, client smoke |

These are four presets spanning three technical routes. pyweixin and wxautox4 share a UIA failure class. wechatbot-new uses replica underneath and would not create independent coverage; its application/Agent/Memory logic and GPL code have not been copied. General UFO/UI-TARS/Agent-S frameworks are not additional dependencies.

## Launch without account access

From the repository root:

```powershell
python -m integrations.wechat.cli catalog
python -m integrations.wechat.workbench
python -m integrations.wechat.cli capture --provider replica --page-size 2 --max-messages 3
python -m integrations.wechat.cli capture --provider replica --page-size 2 --max-messages 20
```

Default execution is synthetic and labelled as such. It neither imports WeChat SDKs nor calls a model. The native workbench is an independent development entry, not a hidden network/native bridge in the sandboxed Demo. The R1 web/desktop shell, database migrations and identity permissions are unchanged.

The workbench lets the operator select a preset/environment, inspect candidate text/source, preview a single reply, and confirm one submission. Mode, target and content changes invalidate its preview. It displays at most 100 live message records; all captured records remain in the candidate file. Closing a busy window waits for completion/timeout instead of falsely claiming cancellation.

For replica, the separate conversation selector reads up to 5000 local sessions and exact matching contact labels. Selecting a row fills its native ID; the teacher need not memorize it. A scope/mode change invalidates that selection. Other presets continue to use the exact visible conversation name; no unsupported listing API is invented.

## Optional dependency environments

Nothing here installs, activates, signs into, or auto-updates third-party software. Do not import a native WeChat package merely to show its setup status. The production backend remains Python 3.13 with its original dependency lock; optional Windows SDK environments should use Python 3.12. Prepare each environment separately after reviewing its upstream dependencies:

```powershell
uv venv --python 3.12 .local-runtime/wechat-env-replica
uv pip install --python .local-runtime/wechat-env-replica/Scripts/python.exe -r integrations/wechat/requirements-replica.txt
```

Use the corresponding requirements file for pyweixin or wxautox4 in a different environment. These files pin the top-level release/source, not every transitive dependency. They are development preparation, not reproducible redistributable SDK bundles. Before live acceptance, record the resolved package inventory and verify the actual installed artifacts/client pairing.

UseChat is a separate Node CLI and native Helper: inspected npm package @shennian/usechat 0.1.0; reviewed source revision 485c8080a0594d1fda5194556ac6da73a5e209a0. Install Helper only by the upstream explicit procedure. Provide a command array consisting of the absolute node executable and absolute CLI entry script; no shell, npx-on-demand download or automatic package installation. Configure the visual model outside this repository. Supply credentials through the provider's supported local configuration/environment, never through command arguments or candidate files.

The catalog checks module discoverability only in the current Python, without import. It is not a readiness or identity check for a separately selected interpreter. A GUI account label is not verification of the currently logged-in account: independently check the client account and exact recipient before use. Duplicate display names remain a live-acceptance blocker.

## Live operator entry (not executed during delivery)

Local account access and model billing are separate choices. No real chats were used in engineering tests. An operator must have the appropriate data-processing permission before choosing live mode; this repository's synthetic policy and formal release Gates are not changed by these switches.

```powershell
$connectorPython = (Resolve-Path -LiteralPath .local-runtime/wechat-env-replica/Scripts/python.exe).Path
python -m integrations.wechat.cli capture --provider replica --account synthetic-selected-directory --chat synthetic-native-chat-id --python $connectorPython --live --max-messages 10000
```

Replace the sample identifiers and use the resolved **absolute** Python executable path. In the workbench use the absolute environment path. For UseChat, live reads additionally require the explicit model authorization checkbox or --allow-model; screenshots may leave the machine for the configured provider and incur charges. There is no model use by default, scheduler, automatic billing or free-service fallback. This laboratory does not enforce a provider-side spending cap; configure that separately before any live model test.

All UI-affecting invocations through this workbench share an exclusive local lock. They cannot prevent a human or unrelated software from moving the mouse, changing the active account, or operating WeChat. Keep a visible unlocked desktop and stop competing automation. A leftover lock after a crash deliberately blocks further work: confirm all previous connector/child processes have stopped before manually removing the fixed classmatter-wechat-desktop.lock file from the operating-system temporary directory. Do not remove it to retry an uncertain send.

## Historical backfill semantics

1. Candidates are scoped by provider, account and conversation. Raw sender/content and evidence class remain distinct; a visual inference is not a native DB row.
2. replica uses newest-first native pagination, keeping shard + local_id as identity. Numeric sender_id == 2 is never treated as proof of self. Unknown senders stay unknown. Account-directory traversal is rejected; the selected SDK account is checked before and after reads because upstream can try other accounts internally. A fallback stops capture instead of returning another account's rows. This check is not an ISB identity proof or a guarantee about the SDK's internal key-discovery accesses.
3. Each added page rechecks the entire earlier captured prefix. New arrivals, content changes, deletions, shard reordering or changed identity stop with source_changed. This conservative algorithm can be expensive for large histories and can repeatedly stop on an active group. It does not offer an atomic snapshot of a changing database.
4. A durable checkpoint is replaced only after a validated page. A timeout/crash retains prior pages. Rerun with a higher max-messages to continue. Cancellation has an explicit service callback and retains a checkpoint; the UI currently uses bounded timeout, not an immediate-cancel button.
5. After source_changed, explicitly select restart in the workbench or pass --restart. The previous candidate is archived under a unique name, never deleted. New and old scans are separate observations, not an automatically merged fact history.
6. Short/empty trailing native DB pages produce source-exhausted for that accessible local source. An empty first read is refused as empty_or_unavailable_source, because an unknown chat or unavailable database must not masquerade as a complete empty archive. complete remains false: deleted messages, unsynchronized older device records, missing shards and undownloaded original attachments cannot be promised. Attachment metadata/placeholders are preserved; binaries are not automatically downloaded.
7. UIA/vision results always retain unknown exhaustion. Repeated identical bubbles are retained within a capture using occurrence identities. Cross-provider or cross-scan automatic deduplication is deliberately not claimed without trustworthy native identity.

Maximum 100000 messages, page size 1–500, candidate file 64 MB. The operator sets bounded scan sizes; API workers have a bounded timeout. Native SDK errors produce fixed codes, not raw keys, paths or chat dumps. The read adapter preserves local SDK caches under upstream ownership: this repository does not claim that changing or deleting its candidate file erases upstream key/decryption caches.

## Send preview and reconciliation

The GUI requires preview followed by a single confirmation. CLI equivalents are prepare-send and send with identical provider/account/chat/text/request-id plus the preview's approval-hash. This digest binds a local operator preview; it is not ISB authentication, a reusable Agent permission, or proof of a genuine verified recipient.

Before invoking the SDK, the runtime exclusively creates a provider-independent outbound receipt. The same account/chat/request-id cannot be retried through another connector. A crash, timeout or exception leaves unknown. A successful SDK call is only submitted-unconfirmed, never delivered/verified. There is no automatic retry, fallback, recall or acknowledgement inference. Changing account aliases or creating a new request ID is outside this idempotency claim; manual reconciliation must precede any new attempt.

replica has no send method exposed beyond a fixed send_not_supported error. Attachment sending, group broadcasting, unsolicited contact and automatic replies are not part of this unit.

## Files, lifecycle and boundary

The default local root is .local-runtime/wechat with separate synthetic/live directories. The caller may choose a trusted local root. Candidate files contain message text and source identifiers; outbound receipts contain digests/status, not message text. These files are not encrypted by this workbench and are not covered by business backup, exit packages, retention or ISB access control. Use them only under appropriate local controls; do not sync them to GitHub or treat them as production storage.

No HTTP route, native IPC, production database connection, Agent registration or business-write tool is added. The next integration gate is an explicitly designed Capture/Review Inbox lifecycle with verified account/entity binding, scoped identity authorization, retention/erasure/exit, provenance and BCG-approved promotion. This must be a subsequent separately accepted slice; consuming these JSON files directly as Domain Facts would violate the existing architecture.

## Acceptance and rollback

Run the offline contract/failure matrix and native synthetic UI smoke:

```powershell
python -m unittest discover -s scripts/tests -p test_wechat_connectors.py -v
python -m integrations.wechat.workbench --smoke
```

The tests also run through the existing root unittest discovery in Windows/Ubuntu CI. Native Tk smoke requires a Windows desktop and is a separate local check. No new skip or weakened existing CI/Gate is introduced.

Live acceptance remains pending for every preset: exact client/SDK/environment, correct active account and recipient (including duplicate names), message/sender accuracy, history boundary/missing media, manual desktop interference, timeout/restart, unknown-send reconciliation, model latency/cost and actual teacher operation burden. No account-ban experiment or ban-rate claim substitutes for these checks.

| Engineering acceptance | Code and reproducible evidence | Formal trace impact |
| --- | --- | --- |
| WX-01: four explicit presets, no implicit imports/install | model.py, providers.py; ProviderTests and catalog test | Separate connector experiment; no frozen requirement/task redefinition |
| WX-02: bounded historical backfill and checkpoint | runtime.py capture; CaptureTests backfill, exact-multiple tail, fault and resume | Capture candidate only, not Domain Fact or QG data |
| WX-03: account/source drift refuses continuation | Scope/Replica guards; account, shard and prefix mutation tests | Existing ISB/QG/BCG authority preserved |
| WX-04: no duplicate uncertain submission | approval/submit; timeout/cross-provider/pending-receipt tests | No Agent tool or business write added |
| WX-05: no model/account use by default | cli.py isolation, default synthetic tests, actual rejected worker subprocess | Synthetic development only; no formal Eval/Gate promotion |
| WX-06: native operator loop | workbench.py; Windows synthetic native smoke | Separate entry, R1 application and Demo unchanged |
| WX-07: public review and source integrity | PUBLIC_MANIFEST, public_guard, pinned history scan, docs checks | Default-deny retained; no dependency code/binary published |

Rollback reverts this independent branch's code/docs; no schema or user instance has been migrated. Keep local candidate/receipt files for reconciliation until the operator explicitly disposes of them. Do not delete an uncertain outbound receipt to make a retry possible.

## Upstream evidence and source ownership

Adapters are original ClassMatter code using public call signatures; no upstream implementations, binaries, credentials, real chat exports or external SKILL instructions are copied or installed.

- [UseChat architecture and protocol](https://github.com/CosmosShadow/usechat/blob/485c8080a0594d1fda5194556ac6da73a5e209a0/docs/ARCHITECTURE.md): visible read, model use and local candidate boundary; MIT.
- [pyweixin inspected source](https://github.com/Hello-Mr-Crab/pywechat/commit/203e9b8e70a9da4e29c82761851f0d440680ebe8): current GitHub API; PyPI 1.9.8 predates these fixes. Repository LICENSE text is LGPL 2.1 while packaging classifiers mention LGPLv3; bundling/commercial redistribution needs clarification, not an invented permissive license.
- [replica 1.2.9 source](https://github.com/fanyuantaier/wechatauto-replica/commit/bc2e6f2461330eb1a53996d2f2afc18416376b52): local DB pagination, shard identities and GUI hot activation. Adapter imports the DB submodule only; Apache-2.0. A read-only implementation does not establish account safety.
- [wxautox4 installation and boundaries](https://docs.wxauto.org/docs/install.html) and [41.2.2 package](https://pypi.org/project/wxautox4/41.2.2/): optional activated commercial SDK, not a bundled open-source core.
- [wechatbot-new application](https://github.com/fanyuantaier/wechatbot-new): recent application fixes and historical style learning are references only; GPL-3.0-or-later, not included as ClassMatter runtime.
