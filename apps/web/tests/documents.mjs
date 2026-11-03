import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomUUID } from 'node:crypto';
import { build } from 'vite';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/documents.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const chunk = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const { documentClient } = await import(`data:text/javascript;base64,${Buffer.from(chunk.code).toString('base64')}`);
const session = { schema_version: 'class-os.identity.v1', csrf_token: randomUUID(),
  subject: { owner_id: randomUUID(), workspace_id: randomUUID() } };
const scope = { class_id: randomUUID(), term_id: randomUUID() }, documentId = randomUUID();
const client = documentClient(session, scope), instant = '2026-11-04T00:00:00Z';
const binding = { workspace_id: session.subject.workspace_id, ...scope };
const payload = () => ({ ...scope, document_id: documentId, command: 'document.create', title: 'synthetic draft',
  body: 'editable text', format: 'plain-text' });
const proposal = () => ({ schema_version: 'classmatter.document-preview.v1', proposal_id: randomUUID(),
  payload_hash: 'a'.repeat(64), risk: 'W2', expires_at: instant, payload: payload() });
const revision = () => ({ version: 1, status: 'draft', title: 'synthetic draft', body: 'editable text', format: 'plain-text',
  operation: 'document.create', created_by: session.subject.owner_id, created_at: instant });
const current = () => ({ schema_version: 'classmatter.document.v1', content_authority: 'working-draft',
  workspace_id: binding.workspace_id, data: { ...revision(), ...scope, document_id: documentId, updated_at: instant } });
const response = value => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } });

test('document read is one scoped private GET and immutable, with no mock fallback', async () => {
  const original = globalThis.fetch, calls = [];
  try {
    globalThis.fetch = async (path, options) => { calls.push([path, options]); return response(current()); };
    const value = await client.read(documentId);
    assert.equal(value.body, 'editable text'); assert(Object.isFrozen(value));
    assert.equal(calls.length, 1); assert.equal(calls[0][1].method, 'GET');
    assert.equal(calls[0][1].credentials, 'same-origin'); assert.equal(calls[0][1].redirect, 'error');
    assert(calls[0][0].endsWith(`/documents/${documentId}`));
  } finally { globalThis.fetch = original; }
});

test('foreign identities, class/term/document, authority injection and impossible dates fail closed', async () => {
  const original = globalThis.fetch;
  try {
    for (const mutate of [v => v.workspace_id = randomUUID(), v => v.data.class_id = randomUUID(),
      v => v.data.term_id = randomUUID(), v => v.data.document_id = randomUUID(), v => v.data.created_by = randomUUID(),
      v => v.content_authority = 'domain-data', v => v.data.sql = 'SELECT 1',
      v => v.data.created_at = '2026-02-30T00:00:00Z', v => v.data.version = true]) {
      const value = current(); mutate(value);
      globalThis.fetch = async () => response(value);
      await assert.rejects(client.read(documentId), /范围、版本或契约/);
    }
  } finally { globalThis.fetch = original; }
});

test('preview binds every submitted field; approval does not commit automatically', async () => {
  const original = globalThis.fetch, calls = [], view = proposal();
  try {
    globalThis.fetch = async (path, options) => { calls.push([path, JSON.parse(options.body)]);
      return response(path.endsWith('/preview') ? view : { schema_version: 'classmatter.document-approval.v1', approval: randomUUID() }); };
    const accepted = await client.preview(payload());
    assert.equal(accepted.payload.document_id, documentId);
    await client.approve(accepted);
    assert.equal(calls.length, 2); assert(calls.every(([path]) => !path.endsWith('/commit')));
    for (const changed of [{ ...payload(), title: 'different' }, { ...payload(), body: 'different' }]) {
      await assert.rejects(client.preview(changed), /范围、版本或契约/);
    }
    const before = calls.length;
    await assert.rejects(client.preview({ ...payload(), class_id: randomUUID() }), /范围、版本或契约/);
    await assert.rejects(client.preview({ ...payload(), risk: 'W1' }), /范围、版本或契约/);
    assert.equal(calls.length, before);
  } finally { globalThis.fetch = original; }
});

test('lost commit is never replayed; original request status must bind proposal, hash and resource/version', async () => {
  const original = globalThis.fetch, calls = [], view = proposal(), key = randomUUID();
  const receipt = { receipt_id: randomUUID(), resource_id: documentId, version: 1 };
  const status = { schema_version: 'class-os.command-status.v1', proposal_id: view.proposal_id,
    payload_hash: view.payload_hash, status: 'committed', receipt };
  try {
    globalThis.fetch = async (path, options) => { calls.push([path, options.method]);
      if (options.method === 'POST') throw new Error('synthetic delivery lost');
      return response(status); };
    await assert.rejects(client.commit(view, key, randomUUID()), /delivery lost/);
    assert.equal(calls.length, 1);
    assert.equal((await client.status(view, key)).receipt.receipt_id, receipt.receipt_id);
    assert.deepEqual(calls.map(([, method]) => method), ['POST', 'GET']);
    for (const mutate of [v => v.proposal_id = randomUUID(), v => v.payload_hash = 'b'.repeat(64),
      v => v.receipt.resource_id = randomUUID(), v => v.receipt.version = 2, v => v.status = 'not_committed']) {
      const value = structuredClone(status); mutate(value);
      globalThis.fetch = async () => response(value);
      await assert.rejects(client.status(view, key), /范围、版本或契约/);
    }
    globalThis.fetch = async () => response({ schema_version: 'classmatter.document-receipt.v1', ...receipt, version: 2 });
    await assert.rejects(client.commit(view, key, randomUUID()), /范围、版本或契约/);
  } finally { globalThis.fetch = original; }
});

test('metadata pages bind scope, snapshot, cursor, unique IDs and exclude bodies', async () => {
  const original = globalThis.fetch;
  const item = { ...scope, document_id: documentId, title: 'synthetic draft', format: 'plain-text',
    status: 'draft', version: 1, created_at: instant, updated_at: instant };
  const page = { schema_version: 'classmatter.document-list.v1', content_authority: 'working-draft', ...binding,
    data: [item], snapshot: 'a'.repeat(64), next_offset: null };
  try {
    globalThis.fetch = async () => response(page);
    assert.equal((await client.list()).data[0].document_id, documentId);
    for (const mutate of [v => v.class_id = randomUUID(), v => v.data[0].term_id = randomUUID(),
      v => v.data.push(v.data[0]), v => v.data[0].body = 'unexpected', v => v.next_offset = 50]) {
      const value = structuredClone(page); mutate(value);
      globalThis.fetch = async () => response(value);
      await assert.rejects(client.list(), /范围、版本或契约/);
    }
    globalThis.fetch = async () => response(page);
    await assert.rejects(client.list({ offset: 50, snapshot: 'b'.repeat(64) }), /范围、版本或契约/);
    await assert.rejects(client.list({ offset: 51, snapshot: page.snapshot }), /范围、版本或契约/);
  } finally { globalThis.fetch = original; }
});

test('history and historical body bind document, author and immutable version', async () => {
  const original = globalThis.fetch, { body: _, ...metadata } = revision();
  try {
    const history = { schema_version: 'classmatter.document-history.v1', content_authority: 'working-draft', ...binding,
      document_id: documentId, data: [metadata], snapshot: 'a'.repeat(64), next_offset: null };
    globalThis.fetch = async () => response(history);
    assert.equal((await client.history(documentId)).data[0].version, 1);
    globalThis.fetch = async () => response({ ...history, document_id: randomUUID() });
    await assert.rejects(client.history(documentId), /范围、版本或契约/);
    const value = { schema_version: 'classmatter.document-revision.v1', content_authority: 'working-draft', ...binding,
      document_id: documentId, data: revision() };
    globalThis.fetch = async () => response(value);
    assert.equal((await client.revision(documentId, 1)).body, 'editable text');
    await assert.rejects(client.revision(documentId, 2), /范围、版本或契约/);
  } finally { globalThis.fetch = original; }
});

test('bounded response, invalid UTF-8, HTTP failure and abort never retry', async () => {
  const original = globalThis.fetch;
  try {
    for (const result of [new Response('x'.repeat(1024 * 1024 + 1), { headers: { 'content-type': 'application/json' } }),
      new Response(new Uint8Array([255]), { headers: { 'content-type': 'application/json' } }),
      new Response('{}', { status: 503, headers: { 'content-type': 'application/json' } }), new Response('<html>wrong')]) {
      let count = 0;
      globalThis.fetch = async () => { count++; return result; };
      await assert.rejects(client.read(documentId)); assert.equal(count, 1);
    }
    const controller = new AbortController(); controller.abort();
    globalThis.fetch = async () => { throw new Error('must not dispatch'); };
    await assert.rejects(client.read(documentId, controller.signal), error => error.name === 'AbortError');
    await assert.rejects(client.read('../escape'), /范围、版本或契约/);
  } finally { globalThis.fetch = original; }
});
