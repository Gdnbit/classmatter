import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomUUID } from 'node:crypto';
import { build } from 'vite';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false, lib: { entry: 'src/runtime/workspace-chat.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const chunk = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(chunk.code).toString('base64')}`);
const session = { csrf_token: 'synthetic-session-' + 'a'.repeat(32), subject: { owner_id: randomUUID(), workspace_id: randomUUID() } };
const client = api.workspaceChatClient(session), threadId = randomUUID(), instant = '2026-11-08T00:00:00Z';
const reply = data => new Response(JSON.stringify(data), { headers: { 'content-type': 'application/json' } });
test('dispatch preference changes only its optional header, preserving the empty body and CSRF', async () => {
  const original = globalThis.fetch, calls = [];
  try {
    globalThis.fetch = async (url, options) => { calls.push({ url, options }); return new Response('', { status: 503 }); };
    for (const effort of [undefined, 'high']) await assert.rejects(client.start(threadId, randomUUID(), new AbortController().signal, () => {}, effort));
    assert.equal(calls.length, 2);
    assert.equal(calls[0].options.headers['x-classmatter-reasoning'], undefined);
    assert.equal(calls[1].options.headers['x-classmatter-reasoning'], 'high');
    for (const { options } of calls) { assert.equal(options.body, '{}'); assert.equal(options.headers['x-class-os-csrf'], session.csrf_token); }
  } finally { globalThis.fetch = original; }
});
function history() {
  return { schema_version: 'classmatter.workspace-chat-history.v1', thread: { thread_id: threadId, title: 'synthetic history', status: 'active', version: 3, created_at: instant, updated_at: instant, cleared_at: null },
    turns: [{ turn_id: randomUUID(), request_id: randomUUID(), ordinal: 1, state: 'completed', version: 3, user_text: 'synthetic user', assistant_text: 'synthetic saved reply',
      candidate: null, candidate_hash: null, action_receipt: null, created_at: instant, started_at: instant, lease_until: '2026-11-08T00:05:00Z', ended_at: instant,
      input_tokens: 10, output_tokens: 8, duration_ms: 100 }], next_before: null };
}
test('workspace history is a private GET, requires no class, and never dispatches a model', async () => {
  const original = globalThis.fetch, calls = [], value = history();
  try {
    globalThis.fetch = async (url, options) => { calls.push({ url, options }); return reply(value); };
    assert.deepEqual(await client.history(threadId), value);
    assert.equal(calls.length, 1); assert.equal(calls[0].options.method, 'GET');
    assert.match(calls[0].url, new RegExp(`/workspace-chat/threads/${threadId}$`));
    assert.equal(calls[0].options.body, undefined);
  } finally { globalThis.fetch = original; }
});
test('scope substitutions, unknown candidate commands and malformed storage replies reject', async () => {
  const original = globalThis.fetch;
  try {
    const value = history();
    for (const invalid of [{ ...value, thread: { ...value.thread, thread_id: randomUUID() } }, { ...value, sql: 'not-a-capability' },
      { ...value, turns: [{ ...value.turns[0], candidate: { command: 'sql.execute', text: 'invalid' }, candidate_hash: 'a'.repeat(64) }] },
      { ...value, turns: [{ ...value.turns[0], state: 'arbitrary' }] }]) {
      globalThis.fetch = async () => reply(invalid);
      await assert.rejects(client.history(threadId));
    }
    globalThis.fetch = async () => new Response('{}', { headers: { 'content-type': 'text/html' } });
    await assert.rejects(client.history(threadId));
  } finally { globalThis.fetch = original; }
});

test('candidate preview binds original hash and every value before confirmation', async () => {
  const original = globalThis.fetch;
  const candidate = { command: 'class.create', class_id: randomUUID(), term_id: randomUUID(), name: 'synthetic class', term_name: 'synthetic term', start_date: '2026-09-01', end_date: '2027-01-30' };
  const turn = { ...history().turns[0], candidate, candidate_hash: 'a'.repeat(64) };
  const value = { schema_version: 'classmatter.workspace-chat-preview.v1', proposal_id: randomUUID(), payload_hash: turn.candidate_hash, risk: 'W2', expires_at: instant, payload: candidate };
  try {
    globalThis.fetch = async () => reply(value);
    assert.equal((await client.preview(threadId, turn)).payload.name, candidate.name);
    for (const invalid of [{ ...value, payload_hash: 'b'.repeat(64) }, { ...value, payload: { ...candidate, name: 'another class' } },
      { ...value, payload: { ...candidate, start_date: '2026-02-31' } }]) {
      globalThis.fetch = async () => reply(invalid); await assert.rejects(client.preview(threadId, turn));
    }
  } finally { globalThis.fetch = original; }
});
test('capability discovery refuses permission/outage fallback and insists on persisted workspace semantics', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response('', { status: 404 }); assert.equal(await api.workspaceChatAvailable(session), false);
    for (const status of [401, 403, 409, 500, 503]) { globalThis.fetch = async () => new Response('', { status }); await assert.rejects(api.workspaceChatAvailable(session)); }
    const value = { schema_version: 'classmatter.workspace-chat-capabilities.v1', profile: 'workspace-chat-d3', memory: 'persisted-not-fact', class_required: false, agent_business_write: false, complete_exit: false };
    globalThis.fetch = async () => reply(value); assert.equal(await api.workspaceChatAvailable(session), true);
    for (const invalid of [{ ...value, agent_business_write: true }, { ...value, class_required: true }, { ...value, memory: 'domain-fact' }]) {
      globalThis.fetch = async () => reply(invalid); await assert.rejects(api.workspaceChatAvailable(session));
    }
  } finally { globalThis.fetch = original; }
});

test('factual comparisons bind candidate hashes and reject invented UI, partial seats and duplicate people', async () => {
  const original = globalThis.fetch;
  const value = history(), candidate = { command: 'seat.layout.create', class_id: randomUUID(), term_id: randomUUID(), layout_id: randomUUID(), rows: 1, columns: 2 };
  const preview = { schema_version: 'classmatter.change-preview.v1', candidate_hash: 'a'.repeat(64), kind: 'seating', fields: [], before_seats: null,
    after_seats: { rows: 1, columns: 2, cells: [{ row: 1, column: 1, student: null, student_id: null }, { row: 1, column: 2, student: null, student_id: null }] } };
  value.turns[0] = { ...value.turns[0], candidate, candidate_hash: preview.candidate_hash, change_preview: preview };
  try {
    globalThis.fetch = async () => reply(value);
    assert.deepEqual((await client.history(threadId)).turns[0].change_preview, preview);
    const person = randomUUID();
    for (const invalid of [{ ...preview, candidate_hash: 'b'.repeat(64) }, { ...preview, html: '<script>invalid</script>' },
      { ...preview, after_seats: { ...preview.after_seats, cells: preview.after_seats.cells.slice(0, 1) } },
      { ...preview, after_seats: { ...preview.after_seats, cells: preview.after_seats.cells.map(cell => ({ ...cell, student: '合成重复', student_id: person })) } },
      { ...preview, kind: 'edit', after_seats: null, fields: [{ field: 'name', before: 'a', after: 'b' }] }]) {
      globalThis.fetch = async () => reply({ ...value, turns: [{ ...value.turns[0], change_preview: invalid }] });
      await assert.rejects(client.history(threadId));
    }
  } finally { globalThis.fetch = original; }
});
