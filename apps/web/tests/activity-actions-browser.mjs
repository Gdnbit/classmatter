import assert from 'node:assert/strict';
import path from 'node:path';
import { writeFileSync } from 'node:fs';
import { chromium, expect as defaultExpect } from '@playwright/test';
import { comparisonContent } from './change-comparison-content.mjs';

const base = process.env.CLASS_OS_TEST_URL;
const expect = defaultExpect.configure({ timeout: 30000 });
const voice = process.env.CLASSMATTER_SYNTHETIC_VOICE === '1';
const previewRace = process.env.CLASSMATTER_PREVIEW_RACE || 'none';
const slowExportPhase = voice || process.env.CLASSMATTER_EXPORT_SLOW_PHASE === '1';
const destination = process.env.CLASSMATTER_TEST_DOWNLOAD_ROOT;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
if (!path.isAbsolute(destination || '')) throw new Error('Owned download directory required');
const browser = await chromium.launch({ headless: true, args: voice ? ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] : [], ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
const observation = { phase: 'start', export: null, steps: [], network: [], navigations: 0 };
const observedAt = performance.now(), requestIds = new WeakMap(); let nextRequest = 0, observedPage;
function snapshot() {
  try { writeFileSync(path.join(destination, 'phase-observation.json'), JSON.stringify(observation)); } catch {}
}
function mark(phase) {
  observation.phase = phase; observation.steps.push({ phase, ms: Math.round(performance.now() - observedAt) });
  if (observation.steps.length > 30) observation.steps.shift();
  snapshot();
}
const stalled = setTimeout(() => { snapshot(); console.error('Chat Office deadline observation', JSON.stringify(observation)); }, 190000);
stalled.unref();
function network(request, state, status = null) {
  const kind = /\/exports\//.test(request.url()) ? 'office' : /\/proposal$/.test(request.url()) ? 'proposal' : /\/workspace-chat\/threads\/[a-f0-9-]+$/.test(request.url()) ? 'history' : null;
  if (!kind) return;
  if (!requestIds.has(request)) requestIds.set(request, ++nextRequest);
  observation.network.push({ id: requestIds.get(request), kind, state, status, ms: Math.round(performance.now() - observedAt) });
  if (observation.network.length > 40) observation.network.shift();
}
try {
  const page = await browser.newPage({ acceptDownloads: true, viewport: { width: 1440, height: 1000 }, ...(voice ? { permissions: ['microphone'] } : {}) }), errors = [], external = [], downloads = [];
  observedPage = page;
  page.on('download', value => { downloads.push(value); mark('download-event'); });
  page.on('request', request => network(request, 'started'));
  page.on('response', response => network(response.request(), 'headers', response.status()));
  page.on('requestfinished', request => network(request, 'finished'));
  page.on('requestfailed', request => network(request, request.failure()?.errorText.includes('ERR_ABORTED') ? 'aborted' : 'failed'));
  page.on('framenavigated', frame => { if (frame === page.mainFrame()) observation.navigations++; });
  if (voice) await page.addInitScript(() => {
    const start = MediaRecorder.prototype.start;
    MediaRecorder.prototype.start = function(...args) {
      window.__voiceBytes = 0;
      this.addEventListener('dataavailable', event => { window.__voiceBytes += event.data.size; });
      return start.apply(this, args);
    };
  });
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url()); });
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息'), cards = page.getByRole('region', { name: '对话中的操作候选', exact: true });
  async function dispatch(message) {
    mark('sending-input');
    await expect(page.locator('form.r1-composer')).toHaveAttribute('data-chat-fresh', 'true');
    const sent = page.waitForResponse(response => response.request().method() === 'POST'
      && /\/workspace-chat\/threads\/[a-f0-9-]+\/turns$/.test(new URL(response.url()).pathname)
      && response.request().postDataJSON()?.text === message);
    const [response] = await Promise.all([sent, page.getByRole('button', { name: '发送消息', exact: true }).click()]);
    assert.equal(response.status(), 200, 'The intended input was actually persisted before expecting a reply');
    mark('input-persisted');
  }
  async function send(message) {
    await expect(page.locator('form.r1-composer')).toHaveAttribute('data-chat-fresh', 'true');
    await input.fill(message); await dispatch(message);
  }
  async function state(expected) {
    await expect.poll(async () => (await page.request.get(base + '/__fixture__/activity')).json()).toEqual(expected);
  }
  async function previewAfterReconnect(card) {
    let release, ready = false, rejectedRead = false, deliveredProposal = Promise.resolve();
    const historyRoute = /\/workspace-chat\/threads\/[a-f0-9-]+$/;
    const rejectHistory = async route => { rejectedRead = true; await route.abort('failed'); };
    const held = new Promise(resolve => release = resolve);
    const holdProposal = route => { deliveredProposal = (async () => {
      const response = await route.fetch();
      assert.equal(response.status(), 200);
      ready = true; mark('genuine-proposal-held'); await held;
      await route.fulfill({ response });
    })(); return deliveredProposal; };
    await page.route('**/turns/*/proposal', holdProposal);
    try {
      await card.getByRole('button', { name: '预览这项操作', exact: true }).click();
      await expect.poll(() => ready).toBe(true);
      await page.context().setOffline(true);
      await page.waitForFunction(() => !navigator.onLine);
      await expect(page.locator('form.r1-composer')).toHaveAttribute('data-chat-fresh', 'false');
      await page.context().setOffline(false);
      await page.waitForFunction(() => navigator.onLine);
      if (previewRace === 'archived') {
        const status = await page.evaluate(async () => {
          const session = await (await fetch('/api/identity/session')).json();
          const url = '/api/workspaces/' + session.subject.workspace_id + '/workspace-chat/threads/' + location.pathname.split('/').at(-1);
          const history = await (await fetch(url)).json();
          return (await fetch(url + '/archive', { method: 'POST', headers: { 'content-type': 'application/json', 'x-class-os-csrf': session.csrf_token },
            body: JSON.stringify({ expected_version: history.thread.version }) })).status;
        });
        assert.equal(status, 200);
      } else if (previewRace === 'history-failure') await page.route(historyRoute, rejectHistory);
      else if (previewRace === 'switch') {
        await page.getByRole('button', { name: '新对话', exact: true }).click();
        await input.fill('尚未发送的新对话草稿');
      }
      const delivered = page.waitForResponse(response => /\/proposal$/.test(response.url()));
      mark('proposal-reconnected'); release();
      await (await delivered).finished();
      const dialog = page.getByRole('dialog', { name: '确认这次变更', exact: true });
      if (previewRace === 'reconnect') await expect(dialog).toBeVisible();
      else {
        if (previewRace === 'archived') {
          await expect(page.locator('form.r1-composer')).toHaveAttribute('data-chat-fresh', 'true');
          await expect(card.getByRole('button', { name: '预览这项操作', exact: true })).toBeDisabled();
        } else if (previewRace === 'history-failure') {
          await expect.poll(() => rejectedRead).toBe(true);
          await expect(page.getByRole('alert').first()).toBeVisible();
          await expect(page.locator('form.r1-composer')).toHaveAttribute('data-chat-fresh', 'false');
        } else {
          await expect(cards).toHaveCount(0);
          await expect(input).toHaveValue('尚未发送的新对话草稿');
        }
        await expect(dialog).toHaveCount(0);
      }
      await state({ records: 0, tasks: 0, status: null, version: null, documents: 0 });
    } finally { release(); await deliveredProposal; await page.unroute('**/turns/*/proposal', holdProposal); await page.unroute(historyRoute, rejectHistory); }
  }
  async function save(index, heading, lostReply = false) {
    mark('preview-' + index);
    const card = cards.nth(index);
    await expect(card.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    const comparison = card.getByRole('region', { name: '变更前后对比', exact: true });
    const before = await comparisonContent(comparison.getByLabel('修改前', { exact: true }));
    const after = await comparisonContent(comparison.getByLabel('待确认的结果', { exact: true }));
    if (index === 0 && previewRace === 'reconnect') await previewAfterReconnect(card);
    else await card.getByRole('button', { name: '预览这项操作', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '确认这次变更', exact: true });
    await dialog.waitFor();
    if (heading === '结束任务') await expect(dialog).toContainText('结束后将移出待办，不能继续修改；记录会保留。');
    const dialogComparison = dialog.getByRole('region', { name: '变更前后对比', exact: true });
    assert.deepEqual(await comparisonContent(dialogComparison.getByLabel('修改前', { exact: true })), before);
    assert.deepEqual(await comparisonContent(dialogComparison.getByLabel('待确认的结果', { exact: true })), after);
    assert(!/[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}|expected_version/.test(await dialog.innerText()));
    if (lostReply) await page.route('**/commands/commit', async route => { await route.fetch(); await route.abort('failed'); }, { times: 1 });
    await dialog.getByRole('button', { name: /^(确认提交|明确批准并提交)$/ }).click();
    if (lostReply) {
      await dialog.getByRole('alert').waitFor();
      await page.getByRole('button', { name: '核对提交结果', exact: true }).click();
    }
    await dialog.waitFor({ state: 'hidden' });
    await card.getByRole('status').filter({ hasText: '已保存' }).waitFor();
    await page.reload();
    assert.deepEqual(await comparisonContent(comparison.getByLabel('修改前', { exact: true })), before);
    assert.deepEqual(await comparisonContent(comparison.getByLabel('已保存的结果', { exact: true })), { ...after, heading: '已保存' });
    mark('saved-refreshed-' + index);
  }
  if (voice) {
    await page.getByRole('button', { name: '语音转文字', exact: true }).click();
    await page.getByRole('button', { name: '完成录音并转文字', exact: true }).waitFor();
    await page.waitForFunction(() => window.__voiceBytes > 0);
    await page.getByRole('button', { name: '完成录音并转文字', exact: true }).click();
    await expect(input).toHaveValue('刚刚合成学生0交来展示作品，记下来，再根据这条记录建立合成作品核对任务。今晚我还要整理自己的书架。');
    await state({ records: 0, tasks: 0, status: null, version: null, documents: 0 });
    await expect(cards).toHaveCount(0);
    await dispatch('刚刚合成学生0交来展示作品，记下来，再根据这条记录建立合成作品核对任务。今晚我还要整理自己的书架。');
  } else await send('刚刚合成学生0交来展示作品，记下来，再根据这条记录建立合成作品核对任务');
  await expect(cards).toHaveCount(1).catch(async error => { throw new Error(await page.locator('body').innerText(), { cause: error }); });
  await state({ records: 0, tasks: 0, status: null, version: null, documents: 0 });
  if (['archived', 'history-failure', 'switch'].includes(previewRace)) {
    await previewAfterReconnect(cards.nth(0));
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    mark('invalidated-proposal-refused');
  } else {
  await save(0, '记录事实');
  await cards.nth(0).getByRole('button', { name: '继续任务', exact: true }).click();
  await expect(cards).toHaveCount(2);
  await state({ records: 1, tasks: 0, status: null, version: null, documents: 0 });
  await save(1, '建立任务');
  await send('合成作品核对先等待，班长正在收集');
  await expect(cards).toHaveCount(3);
  await state({ records: 1, tasks: 1, status: 'not-started', version: 1, documents: 0 });
  await save(2, '修改任务');
  await state({ records: 1, tasks: 1, status: 'waiting', version: 2, documents: 0 });
  await send('结束合成作品核对');
  await page.getByText('请补充实际完成结果。', { exact: true }).waitFor();
  await expect(cards).toHaveCount(3);
  await send('结束合成作品核对，班长交齐，我已核对');
  await page.getByRole('button', { name: '重试回复', exact: true }).click();
  await expect(cards).toHaveCount(4);
  await state({ records: 1, tasks: 1, status: 'waiting', version: 2, documents: 0 });
  await save(3, '结束任务', true);
  await state({ records: 1, tasks: 1, status: 'done', version: 3, documents: 0 });
  await expect(cards.nth(2).getByLabel('已保存的结果', { exact: true })).toContainText('等待别人');
  await send('根据已保存的事实和任务生成合成工作小结');
  await expect(cards).toHaveCount(5);
  await expect(cards.nth(4)).toContainText('班长交齐，我已核对');
  await expect(cards.nth(4).getByRole('button', { name: '导出 Word', exact: true })).toHaveCount(0);
  await expect(cards.nth(4).getByRole('button', { name: '导出 PPT', exact: true })).toHaveCount(0);
  await save(4, '创建工作文档');
  await cards.nth(4).screenshot({ path: path.join(destination, 'saved-chat-card.png') });
  await state({ records: 1, tasks: 1, status: 'done', version: 3, documents: 1 });
  let focusDuringExport = false;
  async function exportSaved(index, version) {
    for (const [label, extension] of [['导出 Word', 'docx'], ['导出 PPT', 'pptx']]) {
      // Hold genuine QG bytes while the original focus handler revalidates
      // history. Background reads must not silently cancel an Office export.
      let release, reached;
      const held = new Promise(resolve => release = resolve), started = new Promise(resolve => reached = resolve);
      const controlled = !focusDuringExport && extension === 'docx';
      let cleanupHistory = async () => {}, officeRequests = 0;
      observation.export = { index, version, extension, controlled, slowExportPhase, navigations: observation.navigations };
      mark('export-start');
      const holdOffice = async route => {
        assert.equal(++officeRequests, 1, 'One click must issue exactly one genuine Office read');
        const response = await route.fetch(); mark('genuine-office-bytes-ready');
        if (slowExportPhase) await new Promise(resolve => setTimeout(resolve, 11000));
        reached(); mark('held-office-response'); await held;
        await route.fulfill({ response }).catch(() => { mark('office-fulfill-cancelled'); });
      };
      // Do not expire/remove interception rules while either real response is
      // paused: disabling Fetch interception can resume that paused request.
      if (controlled) await page.route('**/exports/1/docx', holdOffice);
      let file;
      try {
        const beforeDownload = downloads.length;
        await cards.nth(index).getByRole('button', { name: label, exact: true }).click();
        if (controlled) {
          await expect.poll(() => observation.steps.some(step => step.phase === 'held-office-response')).toBe(true);
          await started; mark('focus-revalidation-start');
          const history = /\/workspace-chat\/threads\/[a-f0-9-]+$/;
          const thread = new URL(page.url()).pathname.split('/').at(-1);
          let releaseHistory, fetchedHistory = 0;
          const historyHeld = new Promise(resolve => releaseHistory = resolve);
          const holdHistory = async route => {
            // Read genuine QG bytes through the route's owned APIResponse,
            // never a CDP body handle belonging to a consumed/cancelled fetch.
            const response = await route.fetch();
            assert.equal(response.status(), 200);
            const value = await response.json();
            assert.equal(value.thread.thread_id, thread);
            assert(value.turns.some(turn => turn.candidate?.command === 'document.create'
              && turn.candidate.document_id === turn.action_receipt?.resource_id && turn.action_receipt.version === version
              && turn.candidate.body.includes('班长交齐，我已核对')));
            fetchedHistory++; mark('genuine-history-bytes-ready'); await historyHeld;
            await route.fulfill({ response }).catch(() => mark('superseded-history-fulfill'));
          };
          await page.route(history, holdHistory);
          cleanupHistory = () => page.unroute(history, holdHistory);
          try {
            await page.evaluate(() => window.dispatchEvent(new Event('focus')));
            await expect.poll(() => fetchedHistory).toBeGreaterThan(0);
            // Hold every new matching read, including a legitimately superseded
            // one, until the actual UI is visibly revalidating. This guarantees
            // the overlap instead of inferring it from network observer timing.
            await expect(page.locator('form.r1-composer')).toHaveAttribute('data-chat-fresh', 'false');
            await expect(cards.nth(index).getByRole('button', { name: label, exact: true })).toHaveText('导出中…');
            await expect(page.getByRole('button', { name: '新对话', exact: true })).toBeEnabled();
            mark('history-refresh-in-progress'); releaseHistory();
            await expect(page.locator('form.r1-composer')).toHaveAttribute('data-chat-fresh', 'true');
            await expect(cards.nth(index).getByLabel('已保存的结果', { exact: true })).toContainText('班长交齐，我已核对');
            mark('new-history-decoded');
          } finally { releaseHistory(); }
          if (slowExportPhase) await new Promise(resolve => setTimeout(resolve, 20000));
          assert.equal(downloads.length, beforeDownload, 'No file before the genuine held response is released');
          assert.equal(observation.navigations, observation.export.navigations, 'No navigation during Office preflight');
          focusDuringExport = true; mark('release-office-response'); release();
        }
        // The listener is installed for the entire test, so no early event is
        // lost. Start the delivery budget AFTER our deliberate response hold,
        // keeping the same 30s actual-file timeout and exact one-file assertion.
        mark('waiting-for-released-file');
        await expect.poll(() => downloads.length, { timeout: 30000 }).toBe(beforeDownload + 1);
        file = downloads[beforeDownload]; mark('download-accepted');
      } finally { mark('export-cleanup'); release(); await cleanupHistory(); if (controlled) await page.unroute('**/exports/1/docx', holdOffice); }
      assert.equal(file.suggestedFilename(), '合成工作小结.' + extension);
      await file.saveAs(path.join(destination, `summary-v${version}.${extension}`));
      assert.equal(await file.failure(), null);
      mark('file-saved');
    }
  }
  await exportSaved(4, 1);
  await send('追加合成工作小结：补充：明天继续展示。');
  await expect(cards).toHaveCount(6);
  await expect(cards.nth(5).getByRole('button', { name: '导出 Word', exact: true })).toHaveCount(0);
  await save(5, '修改工作文档');
  await exportSaved(5, 2);
  const stale = page.waitForResponse(response => /\/exports\/1\/docx$/.test(response.url()));
  await cards.nth(4).getByRole('button', { name: '导出 Word', exact: true }).click();
  assert.equal((await stale).status(), 409);
  await expect(cards.nth(4).getByRole('alert')).toContainText('文档已更新');
  assert.equal(downloads.length, 4);
  // Read-only export must not lock chat switching, and late bytes cannot
  // trigger a download in another thread or page.
  let release, reached;
  const held = new Promise(resolve => release = resolve), started = new Promise(resolve => reached = resolve);
  let lateReady = false;
  const lateOffice = async route => {
    const response = await route.fetch(); lateReady = true; reached(); mark('late-office-bytes-ready');
    await held; await route.fulfill({ response }).catch(() => mark('late-office-cancelled'));
  };
  await page.route('**/exports/2/docx', lateOffice);
  try {
    mark('navigation-cancel-start');
    await cards.nth(5).getByRole('button', { name: '导出 Word', exact: true }).click();
    await expect.poll(() => lateReady).toBe(true);
    await started;
    await page.getByRole('button', { name: '新对话', exact: true }).click();
    await expect(cards).toHaveCount(0);
    await input.fill('尚未发送的小结补充');
    release();
    await expect(input).toHaveValue('尚未发送的小结补充');
  } finally { release(); await page.unroute('**/exports/2/docx', lateOffice); }
  assert.equal(downloads.length, 4);
  mark('navigation-cancel-accepted');
  await page.getByRole('button', { name: '工作', exact: true }).click();
  await page.getByLabel('按状态筛选任务').selectOption('closed');
  await expect(page.getByRole('main').getByRole('button', { name: /合成作品核对/ })).toBeVisible();
  await expect(page.getByRole('region', { name: '事件', exact: true }).getByRole('button', { name: /合成作品核对/ })).toHaveCount(0);
  await page.getByLabel('更多功能', { exact: true }).click();
  await page.getByRole('button', { name: '数据与内容', exact: true }).click();
  await page.getByRole('button', { name: /合成工作小结/ }).first().click();
  await page.getByRole('button', { name: '原文', exact: true }).click();
  await expect(page.locator('.document-text')).toContainText('合成学生0交来展示作品');
  await expect(page.locator('.document-text')).toContainText('班长交齐，我已核对');
  await expect(page.locator('.document-text')).toContainText('补充：明天继续展示。');
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  mark('scenario-accepted');
  }
} catch (error) {
  let view = null;
  // Diagnostics must not wait for chat controls after navigation or replace
  // the original failure with a second locator timeout. Never capture text.
  try { view = await observedPage?.evaluate(() => {
    const form = document.querySelector('form.r1-composer');
    const input = document.querySelector('[aria-label="输入消息"]');
    const send = document.querySelector('button[aria-label="发送消息"]');
    return { fresh: form?.getAttribute('data-chat-fresh') ?? null,
      cardCount: document.querySelectorAll('[aria-label="对话中的操作候选"]').length,
      exporting: [...document.querySelectorAll('button[aria-label="导出 Word"]')].filter(button => button.textContent.includes('导出中')).length,
      draftCharacters: input && 'value' in input ? input.value.length : null,
      sendEnabled: send ? !send.disabled : null };
  }); } catch {}
  console.error('Chat Office phase observation', JSON.stringify({ ...observation, view }));
  throw error;
} finally { clearTimeout(stalled); mark('closing-browser'); await browser.close(); mark('browser-closed'); }
