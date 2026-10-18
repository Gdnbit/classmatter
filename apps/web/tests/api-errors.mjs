import assert from 'node:assert/strict';
import { test } from 'node:test';
import { build } from 'vite';

const output = await build({ configFile: false, logLevel: 'silent', build: { write: false,
  lib: { entry: 'src/runtime/api.ts', formats: ['es'] }, minify: false, target: 'es2022' } });
const bundle = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const api = await import(`data:text/javascript;base64,${Buffer.from(bundle.code).toString('base64')}`);

test('5xx means delivery unknown, never proof of rollback or permission to duplicate a save', async () => {
  const original = globalThis.fetch;
  try {
    for (const status of [500, 502, 503, 504]) for (const body of [undefined, { proposal_id: 'synthetic-proposal', idempotency_key: 'synthetic-key' }]) {
      const calls = [];
      let bodyReads = 0;
      globalThis.fetch = async (url, options) => {
        calls.push({ url, options });
        const response = new Response('synthetic-private-error-canary', { status });
        response.json = response.text = async () => { bodyReads++; throw new Error('Must not adopt an error body'); };
        return response;
      };
      await assert.rejects(api.request('/api/synthetic', body, 'synthetic-csrf'), error => {
        assert(error instanceof api.ApiError && error.status === status);
        assert(error.message.includes('先核对原请求结果，不要重复新建'));
        assert(!/已回滚|未提交|synthetic-private-error-canary/.test(error.message));
        return true;
      });
      assert.equal(bodyReads, 0);
      assert.equal(calls.length, 1);
      assert.equal(calls[0].options.method, body === undefined ? 'GET' : 'POST');
      assert.equal(calls[0].options.credentials, 'same-origin');
      assert.equal(calls[0].options.headers['x-class-os-csrf'], 'synthetic-csrf');
      assert.equal(calls[0].options.body, body === undefined ? undefined : JSON.stringify(body));
    }
  } finally { globalThis.fetch = original; }
});

test('existing identity, conflict and ordinary internal-failure messages remain distinct', () => {
  assert.match(new api.ApiError(401, '').message, /登录已失效/);
  assert.match(new api.ApiError(403, '').message, /本机来源/);
  assert.match(new api.ApiError(409, '').message, /重新预览/);
  assert.match(new api.ApiError(500, '').message, /^请求未完成/);
  assert.match(new api.ApiError(503, '').message, /^服务暂时不可用/);
});
