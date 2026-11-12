import assert from 'node:assert/strict';
import { chromium, expect as defaultExpect } from '@playwright/test';
import { comparisonContent } from './change-comparison-content.mjs';

const base = process.env.CLASS_OS_TEST_URL;
const expect = defaultExpect.configure({ timeout: 30000 });
const voice = process.env.CLASSMATTER_SYNTHETIC_VOICE === '1';
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, args: voice ? ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] : [], ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, ...(voice ? { permissions: ['microphone'] } : {}) }), errors = [], external = [];
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
  async function send(message) { await input.fill(message); await page.getByRole('button', { name: '发送消息', exact: true }).click(); }
  async function state(expected) {
    await expect.poll(async () => (await page.request.get(base + '/__fixture__/activity')).json()).toEqual(expected);
  }
  async function save(index, heading, lostReply = false) {
    const card = cards.nth(index);
    await expect(card.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    const comparison = card.getByRole('region', { name: '变更前后对比', exact: true });
    const before = await comparisonContent(comparison.getByLabel('修改前', { exact: true }));
    const after = await comparisonContent(comparison.getByLabel('待确认的结果', { exact: true }));
    await card.getByRole('button', { name: '预览这项操作', exact: true }).click();
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
  }
  if (voice) {
    await page.getByRole('button', { name: '语音转文字', exact: true }).click();
    await page.getByRole('button', { name: '完成录音并转文字', exact: true }).waitFor();
    await page.waitForFunction(() => window.__voiceBytes > 0);
    await page.getByRole('button', { name: '完成录音并转文字', exact: true }).click();
    await expect(input).toHaveValue('刚刚合成学生0交来展示作品，记下来，再根据这条记录建立合成作品核对任务。今晚我还要整理自己的书架。');
    await state({ records: 0, tasks: 0, status: null, version: null, documents: 0 });
    await expect(cards).toHaveCount(0);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
  } else await send('刚刚合成学生0交来展示作品，记下来，再根据这条记录建立合成作品核对任务');
  await expect(cards).toHaveCount(1).catch(async error => { throw new Error(await page.locator('body').innerText(), { cause: error }); });
  await state({ records: 0, tasks: 0, status: null, version: null, documents: 0 });
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
  await save(4, '创建工作文档');
  await state({ records: 1, tasks: 1, status: 'done', version: 3, documents: 1 });
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
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
} finally { await browser.close(); }
