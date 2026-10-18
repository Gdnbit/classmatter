import assert from 'node:assert/strict';
import { test } from 'node:test';
import { build } from 'vite';
import { randomUUID } from 'node:crypto';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/identity.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const bundle = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(bundle.code).toString('base64')}`);
const csrf = 'synthetic-' + 'a'.repeat(32);
const session = () => ({ schema_version: 'class-os.identity.v1', csrf_token: csrf,
  subject: { owner_id: randomUUID(), workspace_id: randomUUID() } });

test('fixed identity schemas accept actual shapes without modifying input', () => {
  const body = session();
  const before = structuredClone(body);
  assert.deepEqual(api.decodeIdentity('session', body), body);
  assert.deepEqual(body, before);
  const kit = { ...body, recovery_codes: Array.from({ length: 5 }, () => randomUUID() + '.' + 'a'.repeat(32)) };
  assert.deepEqual(api.decodeIdentity('kit', kit), kit);
  assert.equal(api.decodeIdentity('challenge', { schema_version: body.schema_version, csrf_token: csrf }).csrf_token, csrf);
  assert.equal(api.decodeIdentity('signedOut', { schema_version: body.schema_version, status: 'signed_out_all' }).status, 'signed_out_all');
});

test('unknown fields, missing fields, invalid UUID, wrong phase and incomplete kits reject', () => {
  for (const mutate of [body => delete body.schema_version, body => body.csrf_token = '',
    body => body.subject.owner_id = 'not-a-uuid', body => body.subject.administrator = true,
    body => body.token = 'synthetic-credential-canary', body => body.recovery_codes = []]) {
    const body = session(); mutate(body);
    const before = structuredClone(body);
    assert.throws(() => api.decodeIdentity('session', body), api.IdentityResponseInvalid);
    assert.deepEqual(body, before);
  }
  for (const count of [0, 4, 6]) assert.throws(() => api.decodeIdentity('kit', {
    ...session(), recovery_codes: Array.from({ length: count }, () => randomUUID() + '.' + 'a'.repeat(32)) }), api.IdentityResponseInvalid);
  const selector = randomUUID();
  assert.throws(() => api.decodeIdentity('kit', { ...session(), recovery_codes: [...'abcde'].map(c => selector + '.' + c.repeat(32)) }), api.IdentityResponseInvalid);
  assert.throws(() => api.decodeIdentity('challenge', session()), api.IdentityResponseInvalid);
});

test('post failures and malformed successful mutations are unknown, never automatically replayed', async () => {
  const original = globalThis.fetch;
  try {
    for (const reply of [() => { throw new TypeError('synthetic-private-canary'); },
      () => new Response(JSON.stringify({ schema_version: 'class-os.error.v1' }), { status: 500 }),
      () => new Response(JSON.stringify(session()))]) {
      const calls = [];
      globalThis.fetch = async (url, options) => { calls.push(options.method); return reply(); };
      await assert.rejects(api.identityRequest('kit', '/api/identity/recovery/reissue', { password: 'synthetic' }, csrf), error => {
        assert(error instanceof api.IdentityOutcomeUnknown);
        assert(!error.message.includes('synthetic-private-canary'));
        return true;
      });
      assert.deepEqual(calls, ['POST', 'GET']);
    }
  } finally { globalThis.fetch = original; }
});

test('read-only session probe uses GET with no mutation body and keeps malformed replies invalid', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/identity/session'); assert.equal(options.method, 'GET');
      assert.equal(options.body, undefined);
      return new Response(JSON.stringify({ schema_version: 'class-os.identity.v1' }));
    };
    await assert.rejects(api.identityRequest('session', '/api/identity/session'), api.IdentityResponseInvalid);
  } finally { globalThis.fetch = original; }
});

test('wrong path, phase and method never send a request', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => { throw new Error('Should not send'); };
    for (const [kind, path, body] of [['session', 'https://must-not-contact.invalid', undefined],
      ['kit', '/api/identity/login', {}], ['session', '/api/identity/session', {}], ['session', '/api/identity/login', undefined]]) {
      await assert.rejects(api.identityRequest(kind, path, body), api.IdentityResponseInvalid);
    }
  } finally { globalThis.fetch = original; }
});

test('logout delivery loss is reconciled once by bound read-only receipt, never by replay', async () => {
  const original = globalThis.fetch;
  try {
    for (const outcome of ['committed', 'not_committed', 'wrong-id', 'extra-field', 'unavailable']) {
      let operation; const calls = [];
      globalThis.fetch = async (url, options) => {
        calls.push(options.method);
        assert.equal(options.headers['x-class-os-csrf'], csrf);
        if (options.method === 'POST') {
          assert.equal(url, '/api/identity/logout');
          operation = JSON.parse(options.body).request_id;
          assert.match(operation, /^[0-9a-f-]{36}$/);
          return new Response('{}', { status: 500 });
        }
        assert.equal(url, '/api/identity/logout/receipts/' + operation);
        assert.equal(options.body, undefined);
        if (outcome === 'unavailable') return new Response('{}', { status: 500 });
        return new Response(JSON.stringify({ schema_version: 'class-os.identity-logout-receipt.v1', action: 'logout',
          request_id: outcome === 'wrong-id' ? randomUUID() : operation,
          status: outcome === 'not_committed' ? 'not_committed' : 'committed',
          ...(outcome === 'extra-field' ? { token: 'synthetic-not-allowed' } : {}) }));
      };
      if (outcome === 'committed') assert.equal((await api.logoutIdentity(csrf)).status, 'signed_out');
      else await assert.rejects(api.logoutIdentity(csrf), api.IdentityOutcomeUnknown);
      assert.deepEqual(calls, ['POST', 'GET']);
    }
  } finally { globalThis.fetch = original; }
});

test('one-time identity output loss can prove commit but never restores a session or recovery kit', async () => {
  const original = globalThis.fetch;
  try {
    for (const outcome of ['committed', 'wrong-id', 'wrong-action', 'replayable', 'numeric-false', 'token']) {
      let operation; const calls = [];
      const body = { password: 'synthetic-test-password' };
      globalThis.fetch = async (url, options) => {
        calls.push(options.method);
        if (options.method === 'POST') {
          operation = JSON.parse(options.body).request_id;
          assert.equal(url, '/api/identity/recovery/reissue');
          return new Response('{}', { status: 500 });
        }
        assert.equal(url, '/api/identity/receipts/recovery_reissue/' + operation);
        assert.equal(options.headers['x-class-os-csrf'], csrf);
        return new Response(JSON.stringify({ schema_version: 'class-os.identity-operation-receipt.v1',
          request_id: outcome === 'wrong-id' ? randomUUID() : operation,
          action: outcome === 'wrong-action' ? 'login' : 'recovery_reissue', status: 'committed',
          result_replayable: outcome === 'replayable' ? true : outcome === 'numeric-false' ? 0 : false,
          ...(outcome === 'token' ? { token: 'synthetic-forbidden' } : {}) }));
      };
      await assert.rejects(api.identityRequest('kit', '/api/identity/recovery/reissue', body, csrf), error => {
        assert(error instanceof api.IdentityOutcomeUnknown);
        assert.equal(error.message.includes('原身份操作已提交'), outcome === 'committed');
        assert.equal(error.message.includes('synthetic-forbidden'), false);
        return true;
      });
      assert.deepEqual(body, { password: 'synthetic-test-password' });
      assert.deepEqual(calls, ['POST', 'GET']);
    }
  } finally { globalThis.fetch = original; }
});

test('a confirmed all-device logout may acknowledge only signed-out state, never identity capability', async () => {
  const original = globalThis.fetch;
  let operation; const calls = [];
  try {
    globalThis.fetch = async (url, options) => {
      calls.push(options.method);
      if (options.method === 'POST') {
        operation = JSON.parse(options.body).request_id;
        return new Response('{}', { status: 409 });
      }
      assert.equal(url, '/api/identity/receipts/logout_all/' + operation);
      return new Response(JSON.stringify({ schema_version: 'class-os.identity-operation-receipt.v1',
        request_id: operation, action: 'logout_all', status: 'committed', result_replayable: false }));
    };
    assert.deepEqual(await api.identityRequest('signedOut', '/api/identity/logout-all', { password: 'synthetic' }, csrf),
      { schema_version: 'class-os.identity.v1', status: 'signed_out_all' });
    assert.deepEqual(calls, ['POST', 'GET']);
  } finally { globalThis.fetch = original; }
});
