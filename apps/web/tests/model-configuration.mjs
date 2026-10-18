import assert from 'node:assert/strict';
import { test } from 'node:test';
import { build } from 'vite';
import { randomUUID } from 'node:crypto';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/model-configuration.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const bundle = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(bundle.code).toString('base64')}`);
const candidate = { protocol: 'responses', model: 'synthetic', base_url: 'https://provider.example.invalid/v1' };
const reply = () => ({ schema_version: 'class-os.model-configuration.v1', status: 'syntax-valid-not-enabled',
  configuration: { ...candidate }, persisted: false, enabled: false, network_tested: false });

test('status is closed and cannot claim configured API without a stored allowed profile', () => {
  const value = { schema_version: 'class-os.model-status.v1', storage_available: true, version: 0,
    candidate_id: null, configuration: null, key_configured: false, network_permitted: false, test_passed: false, mode: 'offline' };
  assert.deepEqual(api.decodeModelStatus(value), value);
  for (const change of [{ api_key: 'synthetic-secret' }, { mode: 'configured-api' }, { key_configured: true }, { version: 1 }, { sealed: 'synthetic-blob' }, { test_passed: 'true' }]) {
    assert.throws(() => api.decodeModelStatus({ ...value, ...change }));
  }
  const missing = { ...value }; delete missing.network_permitted;
  assert.throws(() => api.decodeModelStatus(missing));
});

test('secret is posted only to candidate staging; response contains only a fixed command reference', async () => {
  const original = globalThis.fetch;
  const session = { subject: { workspace_id: randomUUID() }, csrf_token: 'synthetic-csrf' };
  const command = { command: 'model_configuration.save', candidate_id: randomUUID(), expected_version: 0, ...candidate };
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, `/api/workspaces/${session.subject.workspace_id}/agent/configuration/stage`);
      assert.equal(JSON.parse(options.body).api_key, 'synthetic-key');
      assert.equal(options.headers['x-class-os-csrf'], session.csrf_token);
      return new Response(JSON.stringify({ schema_version: 'class-os.model-staged.v1', command }));
    };
    assert.deepEqual(await api.stageModel(session, candidate, 'synthetic-key', 0), command);
    globalThis.fetch = async () => new Response(JSON.stringify({ schema_version: 'class-os.model-staged.v1', command: { ...command, api_key: 'synthetic-key' } }));
    await assert.rejects(api.stageModel(session, candidate, 'synthetic-key', 0));
  } finally { globalThis.fetch = original; }
});

test('unknown model operation never sends a request', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => { throw new Error('Should not send'); };
    await assert.rejects(api.modelControl({}, '../commands/commit', {}));
  } finally { globalThis.fetch = original; }
});

test('fixed configuration reply accepts only syntax-validated, non-enabled, non-persisted result', () => {
  const body = reply(); const before = structuredClone(body);
  assert.deepEqual(api.decodeConfiguration(body, candidate), before);
  assert.deepEqual(body, before);
  for (const mutate of [body => body.enabled = true, body => body.network_tested = true,
    body => body.persisted = true, body => delete body.status, body => body.api_key = 'synthetic-private',
    body => body.configuration.protocol = 'auto', body => body.configuration.model = 'other-model',
    body => body.configuration.base_url = 'https://other.invalid/v1', body => body.configuration.secret = 'synthetic-private']) {
    const value = reply(); mutate(value); const before = structuredClone(value);
    assert.throws(() => api.decodeConfiguration(value, candidate));
    assert.deepEqual(value, before);
  }
});

test('candidate validation goes to same-origin authenticated API once, never supplied URL', async () => {
  const original = globalThis.fetch;
  let calls = 0;
  const session = { schema_version: 'class-os.identity.v1', csrf_token: 'synthetic-csrf',
    subject: { owner_id: randomUUID(), workspace_id: randomUUID() } };
  try {
    globalThis.fetch = async (url, options) => {
      calls++;
      assert.equal(url, `/api/workspaces/${session.subject.workspace_id}/agent/configuration/validate`);
      assert.equal(options.method, 'POST'); assert.equal(options.credentials, 'same-origin');
      assert.equal(options.headers['x-class-os-csrf'], session.csrf_token);
      assert.deepEqual(JSON.parse(options.body), candidate);
      return new Response(JSON.stringify(reply()));
    };
    await api.validateConfiguration(session, candidate);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test('cancelled validation propagates the caller signal and does not retry', async () => {
  const original = globalThis.fetch;
  const controller = new AbortController(); controller.abort();
  let calls = 0;
  try {
    globalThis.fetch = async (url, options) => {
      calls++; assert.equal(options.signal, controller.signal);
      throw new DOMException('Synthetic cancelled', 'AbortError');
    };
    await assert.rejects(api.validateConfiguration({ subject: { workspace_id: randomUUID() }, csrf_token: 'synthetic' }, candidate, controller.signal), { name: 'AbortError' });
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});
