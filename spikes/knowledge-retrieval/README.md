# Synthetic knowledge retrieval experiment

Contributor task: `contributor-tasks/05-knowledge-rag-spike.md` on the proposed
`docs/contributor-task-board` branch. Product baseline: main `61966bb`.
Task was TODO/unassigned at audit; no corresponding open PR was present.
This independent experiment does not claim or change the upstream task board.

## Run

From the repository root, with Python 3.13 (standard library only):

```powershell
python -m unittest discover -s spikes/knowledge-retrieval -p 'test_*.py' -v
python -X utf8 spikes/knowledge-retrieval/demo.py
pwsh -NoProfile -File scripts/verify.ps1 -Suite knowledge-spike
```

The demo registers a fixed synthetic Chinese guide, retrieves a line with a
versioned citation, replaces its source, rejects the cached result, rebuilds,
then withdraws the source and refuses both cached and new evidence.
No user data, network, filesystem writes, database, model or paid API is used
by the experiment (Python may create ordinary bytecode caches).

## Audit and design

The real `/knowledge` route is a future page shell, not a retrieval service.
No existing knowledge search implementation was found in backend or spikes.
The constraints come from LR-KNW-001, LR-DER-001, ADR-009 and the future-only
architecture boundary. T-EVO-007 is related design traceability, not a claim
that its broader dependency graph or formal evals have been implemented.

`SyntheticSources` simulates authoritative documents in memory. Each immutable
version binds workspace, collection, owner, purpose, document ID, validity and
supersession. Exact duplicate delivery is idempotent; substitution, gaps and
rollback are rejected. Withdrawing a version cannot be undone by replaying it.
Publishing a successor always invalidates its predecessor, including when the
successor is future-dated; there is deliberately no fallback to old evidence.
Validity is start-inclusive and end-exclusive, using aware caller-supplied time.

`SyntheticRetrieval` owns one exact scope. Its rebuildable index contains only
references, never independent source bodies. Each search resolves references
against current source version, digest, validity and withdrawal state before
releasing excerpts. Citations identify the complete scope, document, version,
SHA-256 of the original UTF-8 text and one-based original line. Cache consumers
call `validate` immediately before reuse: any changed dependency rejects the
whole cached evidence set with `stale` and no excerpts. Already delivered text
cannot be retracted from a caller's memory.

Matching is deterministic, case-insensitive AND substring matching of Unicode
word terms within a line, ordered by document ID then line. Chinese queries can
use exact phrases. There are no embeddings, semantic ranking or generated
answers. Unsupported queries return `no_answer`; scope mismatch returns
`refused`. Source instructions are returned as quoted evidence only; there is
no execution/tool interface. Query, line, source and result sizes have bounds.

## Boundaries and limitations

This is a single-process, synthetic-only capability experiment. Passing a
`Scope` object is not authentication, authorization or permission to query real
documents. The fake source publisher is not BCG; search is not QG. Nothing is
registered with the production app, HTTP, Agent tools or persistence. A future
integration needs real QG/BCG authorization, read audit, source snapshot/atomic
release rules, trustworthy clock, retention and permission-change invalidation.
Mutable concurrent sources and clock rollback are outside this harness.

Callers must rebuild after new versions/documents become available; an old
index may omit new evidence but cannot release stale evidence. There is no
durable store, source history export, general dependency graph, user interface,
upload/parser, semantic answer quality claim or production scale guarantee.
No schema, dependency, API, official permissions, Release Manifest, Gate, frozen
requirement/eval/task hashes or security review exceptions are changed.
The existing verification entry point adds `knowledge-spike`, also included in
`all`; the existing read-only Windows/Ubuntu CI runs this suite as an extra step.
No previous check, job permission, trigger, timeout or failure rule is changed.

Rollback removes this isolated directory and its reviewed publication entries;
there is no user data or schema migration to undo. Maintainer acceptance and
merge remain necessary before task status can become DONE.
