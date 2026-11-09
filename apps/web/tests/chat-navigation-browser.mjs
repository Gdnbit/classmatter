import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(10000);
const faults = [], external = [], starts = [], cancels = [], clears = [], failures = [], saveReleases = [];
page.on('response', response => { if (response.status() >= 400) failures.push({ path: new URL(response.url()).pathname, status: response.status() }); });
page.on('pageerror', error => faults.push(error.message));
page.on('request', request => {
  if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
  if (request.method() === 'POST' && request.url().endsWith('/events')) starts.push(request.url());
  if (request.method() === 'POST' && request.url().endsWith('/cancel')) cancels.push(request.url());
  if (request.method() === 'POST' && request.url().endsWith('/clear')) clears.push(request.url());
});
const input = page.getByLabel('输入消息'), sidebar = page.getByRole('region', { name: '聊天列表' });
const select = async title => { const button = sidebar.getByRole('button', { name: title, exact: true }); assert(await button.isEnabled()); await button.click(); };
const send = async text => { await input.fill(text); await page.getByRole('button', { name: '发送消息', exact: true }).click(); };
const answer = text => page.getByRole('article', { name: '助手回复' }).getByText(`回复：${text}`, { exact: true });
const idle = () => page.waitForFunction(() => { const button = document.querySelector('button[aria-label="切换模型"]'); return button && !button.disabled; });
async function waitState(predicate) {
  const deadline = Date.now() + 10000;
  let state;
  do {
    state = await (await page.request.get(base + '/__fixture__/state')).json();
    if (predicate(state)) return state;
    await new Promise(resolve => setTimeout(resolve, 50));
  } while (Date.now() < deadline);
  assert.fail('Owned provider state was not reached: ' + JSON.stringify(state));
}
async function holdSave(text) {
  let release, reached;
  const gate = new Promise(resolve => { release = resolve; }), ready = new Promise(resolve => { reached = resolve; });
  saveReleases.push(release);
  await page.route('**/workspace-chat/threads/*/turns', async route => {
    const response = await route.fetch(); reached(); await gate; await route.fulfill({ response });
  }, { times: 1 });
  await send(text);
  let timer;
  try { await Promise.race([ready, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Owned save response was not captured')), 10000); })]); }
  finally { clearTimeout(timer); }
  return release;
}
try {
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await send('会话甲'); await answer('会话甲').waitFor(); const a = new URL(page.url()).pathname;
  await sidebar.getByRole('button', { name: '新对话', exact: true }).click();
  await send('会话乙'); await answer('会话乙').waitFor(); const b = new URL(page.url()).pathname;
  assert.notEqual(a, b);
  // Browser history must not retarget an already-open destructive dialog.
  await page.getByRole('button', { name: '清除聊天正文', exact: true }).click();
  const clearDialog = page.getByRole('dialog', { name: '清除这段聊天正文？', exact: true });
  await clearDialog.waitFor();
  await page.goBack(); await page.waitForURL(base + a);
  await clearDialog.waitFor({ state: 'hidden' });
  await answer('会话甲').waitFor();
  await page.goForward(); await page.waitForURL(base + b);
  await clearDialog.waitFor({ state: 'hidden' });
  await answer('会话乙').waitFor();
  assert.equal(clears.length, 0);
  // New input in the same thread invalidates the opened confirmation too.
  await page.getByRole('button', { name: '清除聊天正文', exact: true }).click();
  const identity = await (await page.request.get(base + '/api/identity/session')).json();
  const threadRoot = `${base}/api/workspaces/${identity.subject.workspace_id}/workspace-chat/threads/${b.split('/').at(-1)}`;
  const headers = { origin: base, 'x-class-os-csrf': identity.csrf_token }, requestId = crypto.randomUUID();
  const queuedResponse = await page.request.post(threadRoot + '/turns', { headers, data: { request_id: requestId, text: '合成外部已保存消息' } });
  assert.equal(queuedResponse.status(), 200);
  const queued = (await queuedResponse.json()).turn;
  assert.equal((await page.request.post(`${threadRoot}/turns/${requestId}/cancel`, { headers, data: { expected_version: queued.version } })).status(), 200);
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await clearDialog.waitFor({ state: 'hidden' });
  await page.getByText('合成外部已保存消息', { exact: true }).waitFor();
  assert.equal(clears.length, 0); assert.equal(starts.length, 2);

  await input.fill('乙的未发送草稿'); await select('会话甲');
  assert.equal(await input.inputValue(), ''); await input.fill('甲的未发送草稿');
  await select('会话乙'); assert.equal(await input.inputValue(), '乙的未发送草稿');
  await page.goBack(); await page.waitForURL(base + a); assert.equal(await input.inputValue(), '甲的未发送草稿');
  await sidebar.getByRole('button', { name: '新对话', exact: true }).click();
  await input.fill('新对话的未发送草稿'); await select('会话乙');
  assert.equal(await input.inputValue(), '乙的未发送草稿');
  await sidebar.getByRole('button', { name: '新对话', exact: true }).click();
  assert.equal(await input.inputValue(), '新对话的未发送草稿');

  await select('会话甲');
  let release = await holdSave('延迟保存甲');
  await select('会话乙'); assert.equal(await input.inputValue(), '乙的未发送草稿'); release();
  await idle(); assert.equal(new URL(page.url()).pathname, b);
  await select('会话甲'); await answer('延迟保存甲').waitFor();
  await sidebar.getByRole('button', { name: '新对话', exact: true }).click();
  release = await holdSave('延迟新会话');
  await select('会话乙'); release(); await idle();
  assert.equal(new URL(page.url()).pathname, b);
  await select('延迟新会话'); await answer('延迟新会话').waitFor();

  await sidebar.getByRole('button', { name: '新对话', exact: true }).click();
  await page.route('**/workspace-chat/threads/*/turns', route => route.abort('failed'), { times: 1 });
  await send('待恢复新会话'); await page.getByRole('button', { name: '恢复消息', exact: true }).waitFor();
  const pendingPath = new URL(page.url()).pathname;
  await select('会话乙'); assert.equal(await input.inputValue(), '乙的未发送草稿');
  await select('待恢复新会话 · 待确认'); assert.equal(new URL(page.url()).pathname, pendingPath);
  await page.getByRole('button', { name: '恢复消息', exact: true }).click();
  await page.getByRole('button', { name: '继续回复', exact: true }).waitFor();
  assert.equal(starts.length, 4); // Recovering input never dispatches a model.
  await page.getByRole('button', { name: '继续回复', exact: true }).click();
  await answer('待恢复新会话').waitFor();

  await select('会话甲'); await send('等待甲');
  await waitState(state => state.calls.includes('等待甲'));
  assert(await sidebar.getByRole('button', { name: '新对话', exact: true }).isEnabled());
  await input.fill('甲等待期间的下一条草稿');
  await select('会话乙'); assert.equal(await input.inputValue(), '乙的未发送草稿');
  assert.equal(await answer('等待甲').count(), 0);
  await send('等待乙');
  await waitState(state => state.calls.includes('等待乙'));
  assert.equal((await (await page.request.get(base + '/__fixture__/state')).json()).active, 2);
  await select('会话甲'); await page.getByRole('button', { name: '停止回复', exact: true }).waitFor();
  assert.equal(await input.inputValue(), '甲等待期间的下一条草稿');
  assert.equal(starts.length, 7); assert.equal(cancels.length, 0);
  await sidebar.getByRole('button', { name: '新对话', exact: true }).click();
  assert.equal(await input.inputValue(), '');
  await input.fill('两个回复运行时的新草稿');
  await select('会话乙');
  await page.request.post(base + '/__fixture__/release/甲');
  await waitState(state => state.active === 1);
  assert.equal(new URL(page.url()).pathname, b);
  assert.equal(await answer('等待甲').count(), 0);
  await select('会话甲'); await answer('等待甲').waitFor();
  assert.equal(await input.inputValue(), '甲等待期间的下一条草稿');
  assert.equal(starts.length, 7); assert.equal(cancels.length, 0);
  await select('会话乙');
  const cancelled = page.waitForResponse(response => response.url().endsWith('/cancel'));
  await page.getByRole('button', { name: '停止回复', exact: true }).click();
  assert.equal((await cancelled).status(), 200);
  await waitState(state => state.active === 0);
  assert.equal(cancels.length, 1); assert(cancels[0].includes(b.split('/').at(-1)));
  await select('会话甲'); await answer('等待甲').waitFor();
  await select('会话乙'); assert.equal(await answer('等待乙').count(), 0);
  await page.reload(); await input.waitFor();
  assert.equal(starts.length, 7);
  await select('会话甲'); await answer('等待甲').waitFor();
  assert.equal(starts.length, 7);
  // Reading earlier messages must not be interrupted by a completed reply.
  await page.request.post(base + '/__fixture__/hold/甲');
  await send('等待甲');
  await waitState(state => state.calls.filter(text => text === '等待甲').length === 2 && state.active === 1);
  await page.setViewportSize({ width: 1440, height: 520 });
  const viewport = page.locator('.r1-conversation-scroll');
  await page.waitForFunction(() => { const node = document.querySelector('.r1-conversation-scroll'); return node && node.scrollHeight - node.clientHeight > 100; });
  await viewport.hover(); await page.mouse.wheel(0, -10000);
  await page.waitForFunction(() => document.querySelector('.r1-conversation-scroll')?.scrollTop < 5);
  await page.request.post(base + '/__fixture__/release/甲');
  await page.getByRole('button', { name: '查看新回复', exact: true }).waitFor();
  assert((await viewport.evaluate(node => node.scrollTop)) < 5);
  await page.getByRole('button', { name: '查看新回复', exact: true }).click();
  await page.waitForFunction(() => { const node = document.querySelector('.r1-conversation-scroll'); return node && node.scrollHeight - node.clientHeight - node.scrollTop <= 48; });
  await page.setViewportSize({ width: 1440, height: 1000 });
  // A background 401 must still invoke the original global identity handler.
  await page.request.post(base + '/__fixture__/hold/甲');
  await send('等待甲');
  await waitState(state => state.calls.filter(text => text === '等待甲').length === 3 && state.active === 1);
  await select('会话乙');
  await page.route(`**/workspace-chat/threads/${a.split('/').at(-1)}`, route => route.fulfill({ status: 401 }), { times: 1 });
  await page.request.post(base + '/__fixture__/release/甲');
  await page.getByRole('button', { name: '登录', exact: true }).waitFor();
  await waitState(state => state.active === 0);
  assert.equal(starts.length, 9); assert.equal(cancels.length, 1);
  assert.deepEqual(faults, []); assert.deepEqual(external, []);
  console.log('PASS drafts, browser history, new chat, concurrent replies, background completion, targeted cancel, reload without redispatch and background identity failure');
} catch (error) {
  await page.screenshot({ path: '../../test-results/interaction-audit-scroll-failure.png' });
  console.error('Owned chat switch failed', page.url(), await page.locator('body').evaluate(element => {
    const copy = element.cloneNode(true); copy.querySelectorAll('input,textarea,pre').forEach(node => node.remove()); return copy.textContent;
  }), await page.locator('.r1-composer').evaluate(element => ({ ...element.dataset })),
  await page.locator('.r1-conversation-scroll').evaluate(node => ({ top: node.scrollTop, height: node.clientHeight, content: node.scrollHeight, ...node.dataset })), failures);
  throw error;
} finally { for (const release of saveReleases) release(); await page.request.post(base + '/__fixture__/release/甲').catch(() => {}); await page.request.post(base + '/__fixture__/release/乙').catch(() => {}); await browser.close(); }
