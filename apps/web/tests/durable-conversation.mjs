import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomUUID } from 'node:crypto';
import { build } from 'vite';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/durable-conversation.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const chunk = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(chunk.code).toString('base64')}`);
const session = { schema_version: 'class-os.identity.v1', csrf_token: 'synthetic-csrf-' + 'a'.repeat(32),
  subject: { owner_id: randomUUID(), workspace_id: randomUUID() } };
const current = { class_id: randomUUID(), term_id: randomUUID() }, threadId = randomUUID();
const client = api.d1Client(session, current);
const author = { origin: 'local-owner', created_by: session.subject.owner_id, last_modified_by: session.subject.owner_id,
  source_workspace_id: null, source_owner_id: null, source_version: null, content_authority: 'user-original' };
const instant = '2026-10-24T00:00:00Z';
function history() {
  const turn = randomUUID(), message = randomUUID();
  return { schema_version: 'classmatter.conversation-history.v2', ...current, student_id: null,
    history: { thread_id: threadId, title: 'synthetic conversation', status: 'active', version: 2, truncated: false,
      messages: [{ message_id: message, turn_id: turn, created_at: instant, content: { role: 'user', origin: 'user-original', text: 'synthetic saved input' } }] },
    thread_attribution: { ...author, content_authority: 'domain-data' }, message_attributions: [{ message_id: message, attribution: author }],
    results: [], next_before: null, turns: [{ turn_id: turn, ordinal: 1, client_request_id: randomUUID(), mode: 'read',
      run: { schema_version: 'classmatter.conversation-run.v1', run_id: randomUUID(), state: 'queued', version: 1,
        created_at: instant, queued_until: '2026-10-24T00:01:00Z', ended_at: null } }] };
}
const response = value => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } });

test('history reconstructs the original queued request using only private GETs, never dispatch', async () => {
  const original = globalThis.fetch, value = history(), calls = [];
  try {
    globalThis.fetch = async (url, options) => { calls.push([url, options]); return response(value); };
    const saved = await client.history(threadId);
    assert.equal(saved.turns[0].client_request_id, value.turns[0].client_request_id);
    assert.equal(calls.length, 1); assert.equal(calls[0][1].method, 'GET');
    assert.equal(calls[0][1].credentials, 'same-origin');
    assert.match(calls[0][0], /\/history$/); assert(!calls[0][0].includes('/events'));
  } finally { globalThis.fetch = original; }
});

test('foreign scope, duplicate/misaligned turns, authority injection and impossible times fail closed', async () => {
  const original = globalThis.fetch;
  try {
    for (const mutate of [v => v.class_id = randomUUID(), v => v.term_id = randomUUID(),
      v => v.history.thread_id = randomUUID(), v => v.turns.push(v.turns[0]),
      v => v.history.messages[0].turn_id = randomUUID(), v => v.turns[0].run.generation = randomUUID(),
      v => v.message_attributions[0].attribution = { ...author, content_authority: 'domain-data' },
      v => v.turns[0].run.state = 'completed', v => v.history.messages[0].created_at = '2026-02-30T12:00:00Z',
      v => v.history.messages[0].content.origin = 'assistant-unverified']) {
      const value = history(); mutate(value);
      globalThis.fetch = async () => response(value);
      await assert.rejects(client.history(threadId));
    }
  } finally { globalThis.fetch = original; }
});

test('only explicit missing capability means R1; rejection or outage never becomes a fallback', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response('', { status: 404 });
    assert.equal(await api.discoverD1(session), 'r1');
    for (const status of [401, 403, 409, 500, 503]) {
      globalThis.fetch = async () => new Response('', { status });
      await assert.rejects(api.discoverD1(session));
    }
    globalThis.fetch = async () => response({ schema_version: 'classmatter.runtime-capabilities.v1', profile: 'conversation-d1',
      data_mode: 'synthetic-only', history_protocol: 'classmatter.conversation-history.v2' });
    assert.equal(await api.discoverD1(session), 'conversation-d1');
  } finally { globalThis.fetch = original; }
});

test('receipt status uses original proposal AND idempotency key, without a new write or retry', async () => {
  const original = globalThis.fetch, key = randomUUID(), proposal = { proposal_id: randomUUID(), payload_hash: 'a'.repeat(64),
    payload: { command: 'conversation.clear', thread_id: threadId, class_id: current.class_id, term_id: current.term_id, expected_version: 2 } };
  try {
    const receipt = { receipt_id: randomUUID(), resource_id: threadId, version: 3 };
    globalThis.fetch = async (url, options) => {
      assert(url.endsWith(`/commands/${proposal.proposal_id}/receipts/${key}`)); assert.equal(options.method, 'GET');
      return response({ schema_version: 'class-os.command-status.v1', proposal_id: proposal.proposal_id, payload_hash: proposal.payload_hash,
        status: 'committed', receipt });
    };
    assert.deepEqual((await client.commandState(proposal, key)).receipt, receipt);
    globalThis.fetch = async () => response({ schema_version: 'class-os.command-status.v1', proposal_id: proposal.proposal_id,
      payload_hash: 'b'.repeat(64), status: 'committed', receipt });
    await assert.rejects(client.commandState(proposal, key));
  } finally { globalThis.fetch = original; }
});

test('aborted or malformed data does not release a late snapshot or issue another request', async () => {
  const original = globalThis.fetch, controller = new AbortController(); let calls = 0;
  try {
    globalThis.fetch = async () => { calls++; controller.abort(); return response(history()); };
    await assert.rejects(client.history(threadId, controller.signal), { name: 'AbortError' });
    assert.equal(calls, 1);
    globalThis.fetch = async () => new Response('{}', { headers: { 'content-type': 'text/html' } });
    await assert.rejects(client.history(threadId));
  } finally { globalThis.fetch = original; }
});
