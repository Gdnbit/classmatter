import assert from 'node:assert/strict';
import { test } from 'node:test';
import { build } from 'vite';
import { randomUUID } from 'node:crypto';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/agent-conversation.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const chunk = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(chunk.code).toString('base64')}`);
const session = { schema_version: 'class-os.identity.v1', csrf_token: 'synthetic-' + 'a'.repeat(32),
  subject: { owner_id: randomUUID(), workspace_id: randomUUID() } };
const context = { class_id: randomUUID(), term_id: randomUUID() };
const frame = student => ({ schema_version: 'class-os.agent-conversation.v2', conversation_id: randomUUID(),
  expires_at: new Date().toISOString(), memory: 'ephemeral-not-fact', ...context, student_id: student });

test('explicit class/student scope is validated and echoed, one private request only', async () => {
  const original = globalThis.fetch;
  try {
    for (const student of [null, randomUUID()]) {
      let calls = 0;
      const controller = new AbortController();
      globalThis.fetch = async (url, options) => {
        calls++;
        assert.equal(url, '/api/workspaces/' + session.subject.workspace_id + '/agent/conversations');
        assert.deepEqual(JSON.parse(options.body), { schema_version: 'class-os.agent-conversation-request.v2', student_id: student });
        assert.equal(options.signal, controller.signal);
        return new Response(JSON.stringify(frame(student)));
      };
      assert.equal((await api.createScopedConversation(session, context, student, controller.signal)).student_id, student);
      assert.equal(calls, 1);
    }
  } finally { globalThis.fetch = original; }
});

test('missing scope, wrong binding, unknown fields, bad time and legacy response never fall back', async () => {
  const original = globalThis.fetch, student = randomUUID();
  try {
    for (const mutate of [value => delete value.student_id, value => value.student_id = null,
      value => value.class_id = randomUUID(), value => value.term_id = randomUUID(),
      value => value.conversation_id = 'not-a-uuid', value => value.token = 'synthetic-forbidden',
      value => value.expires_at = '2026-02-30T12:00:00Z', value => value.schema_version = 'class-os.agent.v1']) {
      let calls = 0; const value = frame(student); mutate(value);
      globalThis.fetch = async () => { calls++; return new Response(JSON.stringify(value)); };
      await assert.rejects(api.createScopedConversation(session, context, student), api.ConversationScopeInvalid);
      assert.equal(calls, 1);
    }
  } finally { globalThis.fetch = original; }
});

test('invalid input or cancellation never releases a late scope or retries a request', async () => {
  const original = globalThis.fetch;
  try {
    let calls = 0;
    globalThis.fetch = async () => { calls++; return new Response('{}'); };
    await assert.rejects(api.createScopedConversation(session, context, 'student-name'), api.ConversationScopeInvalid);
    assert.equal(calls, 0);
    const controller = new AbortController();
    globalThis.fetch = async () => { calls++; controller.abort(); return new Response(JSON.stringify(frame(null))); };
    await assert.rejects(api.createScopedConversation(session, context, null, controller.signal), { name: 'AbortError' });
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

async function noteFrame() {
  const prefix = '🌱开头：', quote = '合成🌱原文', source = prefix + quote + '结束';
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(source));
  return { source, value: { schema_version: 'class-os.record-note-candidate.v1', status: 'unverified-user-note',
    note_quote: quote, source_start: Array.from(prefix).length, source_end: Array.from(prefix + quote).length,
    source_hash: Buffer.from(hash).toString('hex') } };
}

test('record note uses Unicode code-point span and current-message SHA256, never a fact or target', async () => {
  const { source, value } = await noteFrame();
  const parsed = await api.parseRecordNoteCandidate(value, source);
  assert.deepEqual(parsed, value);
  assert(Object.isFrozen(parsed));
  await assert.rejects(api.parseRecordNoteCandidate(value, '另一轮：' + source), api.RecordNoteSourceInvalid);
  for (const change of [frame => frame.note_quote = '编造结论', frame => frame.source_start = false,
    frame => frame.source_end = 1999, frame => frame.source_hash = '0'.repeat(64),
    frame => frame.student_id = randomUUID(), frame => frame.status = 'verified-fact']) {
    const invalid = { ...value }; change(invalid);
    await assert.rejects(api.parseRecordNoteCandidate(invalid, source), api.RecordNoteSourceInvalid);
  }
});

test('late source-digest completion after abort cannot release a record note', async () => {
  const { source, value } = await noteFrame(), controller = new AbortController();
  const pending = api.parseRecordNoteCandidate(value, source, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
});

test('record note snapshot cannot change while native source hashing is pending', async () => {
  const { source, value } = await noteFrame();
  const input = { ...value }, pending = api.parseRecordNoteCandidate(input, source);
  input.note_quote = '原文校验后偷偷替换的内容';
  const parsed = await pending;
  assert.equal(parsed.note_quote, value.note_quote);
  assert.notEqual(parsed, input);
});
