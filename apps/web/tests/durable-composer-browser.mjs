import assert from 'node:assert/strict';
import { build } from 'vite';
import { chromium } from '@playwright/test';
import react from '@vitejs/plugin-react';

// Exercise the real hook and composer without a database, identity secrets or a Provider.
const entry = `
import React from 'react';
import { createRoot } from 'react-dom/client';
import { useDurableConversation } from '/src/runtime/useDurableConversation.ts';
import { DurableComposer } from '/src/runtime/DurableConversation.tsx';
const session = { csrf_token: 'synthetic-session-a', subject: { owner_id: '11111111-1111-4111-8111-111111111111', workspace_id: '22222222-2222-4222-8222-222222222222' } };
let props = { enabled: true, session, classroom: null, threadId: '', readable: true, canWrite: false,
  onSelect() {}, onBusyChange() {}, onDraftChange(value) { window.hasDraft = value; }, onError() {} };
window.requests = [];
window.fetch = (url, options) => { window.requests.push({ url: String(url), method: options?.method || 'GET' }); return new Promise(() => {}); };
const root = createRoot(document.getElementById('root'));
function App() {
  const state = useDurableConversation(props);
  window.send = () => state.send();
  return React.createElement(DurableComposer, { state, students: [], canWrite: props.canWrite });
}
window.scope = value => { props = { ...props, ...value }; root.render(React.createElement(App)); };
window.scope({});
`;
const output = await build({ configFile: false, logLevel: 'silent', define: { 'process.env.NODE_ENV': '"production"' }, plugins: [react(), {
  name: 'synthetic-composer-entry', resolveId: id => id.endsWith('composer-fixture') ? '\0composer-fixture' : null,
  load: id => id === '\0composer-fixture' ? entry : null,
}], build: { write: false, lib: { entry: 'composer-fixture', formats: ['iife'], name: 'ComposerFixture' }, minify: false } });
const chunk = (Array.isArray(output) ? output[0] : output).output.find(item => item.type === 'chunk' && item.isEntry);
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.setContent('<div id="root"></div>');
  await page.addScriptTag({ content: chunk.code });
  await page.waitForSelector('textarea', { timeout: 5000 }).catch(error => { throw new Error(JSON.stringify(errors), { cause: error }); });
  const input = page.getByLabel('输入消息');
  await input.fill('合成建班前草稿');
  assert.equal(await input.inputValue(), '合成建班前草稿');
  assert.match(await page.getByRole('status').innerText(), /发送前.*建立班级/);
  assert.equal(await page.getByRole('button', { name: '发送消息' }).isDisabled(), true);
  await input.press('Enter'); await page.evaluate(() => window.send());
  assert.deepEqual(await page.evaluate(() => window.requests), []);
  await page.evaluate(() => window.scope({ classroom: { class_id: '33333333-3333-4333-8333-333333333333', term_id: '44444444-4444-4444-8444-444444444444' } }));
  await page.waitForFunction(() => window.requests.length >= 1);
  assert.equal(await input.inputValue(), '合成建班前草稿');
  assert.equal(await page.getByRole('button', { name: '发送消息' }).isDisabled(), true);
  assert.equal(await page.evaluate(() => window.hasDraft), true);
  await page.evaluate(() => window.scope({ classroom: { class_id: '55555555-5555-4555-8555-555555555555', term_id: '44444444-4444-4444-8444-444444444444' } }));
  await page.waitForFunction(() => document.querySelector('textarea').value === '');
  await page.evaluate(() => window.scope({ classroom: null }));
  await input.fill('合成身份切换前草稿');
  await page.evaluate(() => window.scope({ session: { csrf_token: 'synthetic-session-b', subject: { owner_id: '11111111-1111-4111-8111-111111111111', workspace_id: '22222222-2222-4222-8222-222222222222' } } }));
  await page.waitForFunction(() => document.querySelector('textarea').value === '');
  assert((await page.evaluate(() => window.requests)).every(item => item.method === 'GET'));
  assert.deepEqual(errors, []);
  console.log('PASS unassigned local input; no dispatch; first class preserves draft; class/session changes clear; no writes or Provider');
} finally { await browser.close(); }
