import assert from 'node:assert/strict';
import { build } from 'vite';
import { chromium } from '@playwright/test';
import react from '@vitejs/plugin-react';

// Exercise the real hook and composer without a database, identity secrets or a Provider.
const entry = `
import React from 'react';
import { createRoot } from 'react-dom/client';
import { useDurableConversation } from '/src/runtime/useDurableConversation.ts';
import { DurableComposer, DurableHistory } from '/src/runtime/DurableConversation.tsx';
const session = { csrf_token: 'synthetic-session-a', subject: { owner_id: '11111111-1111-4111-8111-111111111111', workspace_id: '22222222-2222-4222-8222-222222222222' } };
let props = { enabled: true, session, classroom: null, threadId: '', readable: true, canWrite: false, canChat: true,
  onSelect() {}, onBusyChange() {}, onDraftChange(value) { window.hasDraft = value; }, onError(error) { window.lastError = String(error); } };
window.requests = [];
window.fetch = async (url, options) => {
  window.requests.push({ url: String(url), method: options?.method || 'GET', body: options?.body });
  if (String(url).endsWith('/workspace-conversations')) return new Response(JSON.stringify({ schema_version: 'classmatter.workspace-conversation.v1', conversation_id: '66666666-6666-4666-8666-666666666666', expires_at: new Date(Date.now()+60000).toISOString(), memory: 'ephemeral-not-fact', scope: 'workspace' }), { headers: { 'content-type': 'application/json' } });
  if (String(url).endsWith('/agent/events')) {
    if(window.slow) return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
    const events = [{ type: 'run.started', payload: {} }, { type: 'message.delta', payload: { text: '合成普通聊天回复', source_refs: [] } }, { type: 'run.completed', payload: {} }];
    return new Response(events.map((event,index)=>'id: '+(index+1)+'\\nevent: '+event.type+'\\ndata: '+JSON.stringify({ ...event, cursor: index+1, run_id: 'synthetic-run' })+'\\n\\n').join(''), { headers: { 'content-type':'text/event-stream' } });
  }
  if (String(url).endsWith('/conversations') && (!options?.method || options.method === 'GET')) {
    return new Response(JSON.stringify({ schema_version: 'classmatter.conversation-list.v1', snapshot: 'a'.repeat(64), next_offset: null,
      data: [{ thread_id: '77777777-7777-4777-8777-777777777777', title: '合成旧对话-' + props.classroom.class_id, status: 'active', version: 1,
        student_id: null, updated_at: '2026-11-08T00:00:00Z', attribution: { origin: 'local-owner', created_by: props.session.subject.owner_id,
          last_modified_by: props.session.subject.owner_id, source_workspace_id: null, source_owner_id: null, source_version: null, content_authority: 'domain-data' } }] }), { headers: { 'content-type':'application/json' } });
  }
  return new Promise(() => {});
};
const root = createRoot(document.getElementById('root'));
function App() {
  const state = useDurableConversation(props);
  window.legacyTitles = state.listing?.data.map(item => item.title) || [];
  window.chatIsWorkspace = state.workspaceChat;
  window.send = () => state.send();
  return React.createElement(React.Fragment, null, React.createElement(DurableHistory, { state, canWrite: props.canWrite, onDraft() {} }), React.createElement(DurableComposer, { state, students: [], canWrite: props.canWrite }));
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
  assert.equal(await page.getByLabel('对话方式').inputValue(), 'chat');
  assert.equal(await page.getByRole('button', { name: '发送消息' }).isEnabled(), true);
  await page.locator('form').evaluate(form => { form.requestSubmit(); form.requestSubmit(); });
  await page.getByRole('status').filter({ hasText: '回复完成' }).waitFor({ timeout: 5000 }).catch(async error => { throw new Error(JSON.stringify(await page.evaluate(() => ({ error: window.lastError, requests: window.requests, body: document.body.innerText }))), { cause: error }); });
  assert.equal(await page.locator('article.assistant p').innerText(), '合成普通聊天回复');
  assert.equal((await page.evaluate(() => window.requests)).length, 2);
  await input.fill('合成建班前草稿');
  await page.evaluate(() => window.scope({ classroom: { class_id: '33333333-3333-4333-8333-333333333333', term_id: '44444444-4444-4444-8444-444444444444' } }));
  assert.equal(await input.inputValue(), '合成建班前草稿');
  assert.equal(await page.evaluate(() => window.hasDraft), true);
  await page.waitForFunction(() => window.legacyTitles[0] === '合成旧对话-33333333-3333-4333-8333-333333333333');
  assert.equal(await page.evaluate(() => window.chatIsWorkspace), true);
  await page.evaluate(() => window.scope({ classroom: { class_id: '55555555-5555-4555-8555-555555555555', term_id: '44444444-4444-4444-8444-444444444444' } }));
  assert.equal(await input.inputValue(), '合成建班前草稿');
  await page.waitForFunction(() => window.legacyTitles[0] === '合成旧对话-55555555-5555-4555-8555-555555555555');
  await input.press('Enter');
  await page.waitForFunction(() => document.querySelectorAll('article.assistant').length === 2);
  assert.equal((await page.evaluate(() => window.requests)).filter(item => item.url.endsWith('/workspace-conversations')).length, 1);
  await input.fill('合成身份切换前草稿');
  await page.evaluate(() => window.scope({ session: { csrf_token: 'synthetic-session-b', subject: { owner_id: '11111111-1111-4111-8111-111111111111', workspace_id: '22222222-2222-4222-8222-222222222222' } } }));
  await page.waitForFunction(() => document.querySelector('textarea').value === '' && document.querySelectorAll('article').length === 0);
  await page.evaluate(() => window.scope({ classroom: null }));
  await page.waitForFunction(() => window.legacyTitles.length === 0);
  await page.getByLabel('对话方式').selectOption('read');
  await input.fill('没有班级不能查询');
  assert.equal(await page.getByRole('button', { name: '发送消息' }).isDisabled(), true);
  await page.getByLabel('对话方式').selectOption('chat');
  await page.evaluate(() => { window.slow = true; });
  await input.fill('取消普通聊天'); await input.press('Enter');
  await page.getByRole('button', { name: '停止回复' }).click();
  await page.getByRole('status').filter({ hasText: '已停止' }).waitFor();
  await page.waitForFunction(() => !document.querySelector('textarea').disabled);
  // Startup discovers the compatible class history after enabling the hook.
  // Its list must survive the initial identity/epoch reset as well as switches.
  await page.evaluate(() => window.scope({ enabled: false }));
  await page.waitForFunction(() => window.legacyTitles.length === 0 && document.querySelectorAll('article').length === 0);
  await page.evaluate(() => window.scope({ enabled: true, classroom: { class_id: '33333333-3333-4333-8333-333333333333', term_id: '44444444-4444-4444-8444-444444444444' } }));
  await page.waitForFunction(() => window.legacyTitles[0] === '合成旧对话-33333333-3333-4333-8333-333333333333');
  assert.equal(await page.evaluate(() => window.chatIsWorkspace), true);
  assert((await page.evaluate(() => window.requests)).every(item => /\/agent\/(workspace-conversations|events)$/.test(item.url)
    || item.method === 'GET' && item.url.endsWith('/conversations') && item.body === undefined));
  assert.deepEqual(errors, []);
  console.log('PASS ordinary chat without class; double-submit once; multi-turn and class independence; identity isolation; cancel; class query refused; no business writes/Provider');
} finally { await browser.close(); }
