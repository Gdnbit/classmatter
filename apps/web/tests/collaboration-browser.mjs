import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';

const bases = [process.env.CLASS_OS_TEST_URL_A, process.env.CLASS_OS_TEST_URL_B];
if (bases.some(base => !/^http:\/\/127\.0\.0\.1:\d+$/.test(base || ''))) throw new Error('Two disposable synthetic instances required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
const errors = [], external = [];
try {
  const contexts = await Promise.all(bases.map(() => browser.newContext({ viewport: { width: 1440, height: 900 } })));
  for (const [i, context] of contexts.entries()) await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: bases[i] });
  const pages = await Promise.all(contexts.map(context => context.newPage()));
  for (const [i, page] of pages.entries()) {
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (/^https?:/.test(request.url()) && !request.url().startsWith(bases[i] + '/')) external.push(request.url()); });
    await page.goto(bases[i]);
    await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await expect(page.getByLabel('输入消息')).toBeEnabled();
  }
  const [a, b] = pages, invitations = [];
  for (const [i, page] of pages.entries()) {
    await page.getByRole('button', { name: '设置', exact: true }).click();
    const settings = page.getByRole('dialog', { name: '设置', exact: true });
    await settings.getByLabel('我的称呼', { exact: true }).fill(i ? '合成王老师' : '合成李老师');
    await settings.getByRole('button', { name: '生成协作邀请', exact: true }).click();
    await settings.getByRole('button', { name: '复制邀请', exact: true }).click();
    await expect(settings.getByRole('status').filter({ hasText: '已复制邀请' })).toBeVisible();
    invitations.push(await page.evaluate(() => navigator.clipboard.readText()));
    assert.equal(JSON.parse(invitations.at(-1)).name, i ? '合成王老师' : '合成李老师');
    await expect(settings.getByLabel('协作邀请', { exact: true })).toHaveCount(0);
    assert(!invitations.at(-1).includes('private_key'));
    await settings.getByRole('button', { name: '关闭设置', exact: true }).click();
  }
  for (const [i, page] of pages.entries()) {
    await page.getByRole('button', { name: '设置', exact: true }).click();
    const settings = page.getByRole('dialog', { name: '设置', exact: true });
    await settings.getByRole('button', { name: '添加同事', exact: true }).click();
    await settings.getByLabel('同事的邀请', { exact: true }).fill(invitations[1 - i]);
    await settings.getByRole('button', { name: '核对同事', exact: true }).click();
    await expect(settings.getByRole('region', { name: '同事协作', exact: true })).toContainText(i ? '合成李老师' : '合成王老师');
    await settings.getByRole('button', { name: '确认添加', exact: true }).click();
    await settings.getByRole('button', { name: '停止协作', exact: true }).waitFor();
    await settings.getByRole('button', { name: '关闭设置', exact: true }).click();
  }
  const card = (page, title) => page.getByRole('region', { name: '对话中的操作候选', exact: true }).filter({ has: page.getByRole('heading', { name: title, exact: true }) }).last();
  async function send(page, text) {
    await page.getByLabel('输入消息').fill(text);
    await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeEnabled();
    await expect(page.getByLabel('输入消息')).toHaveValue(text);
    await page.getByLabel('输入消息').press('Enter');
    await expect(page.getByRole('article', { name: '你的消息', exact: true }).last()).toContainText(text);
  }
  async function confirm(page, current, loseResponse = false) {
    await current.getByRole('button', { name: '预览这项操作', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '确认这次变更', exact: true });
    await dialog.waitFor();
    if (loseResponse) await page.route('**/commands/commit', async route => {
      await route.fetch(); await route.abort('failed'); await page.unroute('**/commands/commit');
    }, { times: 1 });
    await dialog.getByRole('button', { name: '明确批准并提交', exact: true }).click();
    if (loseResponse) {
      await expect(dialog.getByRole('button', { name: '核对提交结果', exact: true })).toBeEnabled();
      await dialog.getByRole('button', { name: '核对提交结果', exact: true }).click();
    }
    await expect(dialog).toHaveCount(0);
    await expect(current.getByRole('status').filter({ hasText: '已保存' })).toBeVisible();
  }
  await send(a, '请向合成王老师收集本周数学教学进度，补入小结。');
  const request = card(a, '收集同事材料');
  await request.waitFor({ timeout: 25000 });
  await expect(request.getByLabel('待确认的结果', { exact: true })).toContainText('合成王老师');
  await confirm(a, request);
  const pathA = new URL(a.url()).pathname;
  await expect(a.getByRole('region', { name: '材料协作', exact: true })).toContainText('等待补充', { timeout: 25000 });
  await b.getByLabel('输入消息').fill('另一条未发送的草稿');
  const inbox = b.getByRole('region', { name: '聊天列表', exact: true }).getByRole('button').filter({ hasText: '合成李老师：收集：本周数学教学进度' });
  await inbox.waitFor({ timeout: 25000 });
  await expect(b.getByLabel('输入消息')).toHaveValue('另一条未发送的草稿');
  assert.equal(new URL(b.url()).pathname, '/', 'Inbound material request must not steal focus');
  await inbox.click();
  await expect(b.getByRole('article', { name: '你的消息', exact: true })).toHaveCount(0);
  await expect(b.getByRole('article', { name: '助手回复', exact: true })).toContainText('合成李老师希望补充：本周数学教学进度');
  await b.getByRole('button', { name: '新对话', exact: true }).click();
  await expect(b.getByLabel('输入消息')).toHaveValue('另一条未发送的草稿');
  await b.getByLabel('输入消息').fill(''); await inbox.click();
  await send(b, '提供本周教学进度给合成李老师。');
  const reply = card(b, '提供材料');
  await reply.waitFor({ timeout: 25000 });
  await expect(reply).toContainText('数学完成第三单元，周五已核对练习。');
  await expect(reply.getByLabel('待确认的结果', { exact: true })).toContainText('合成李老师');
  await confirm(b, reply);
  const summary = card(a, '保存班级工作小结');
  await summary.waitFor({ timeout: 25000 });
  await expect(summary).toContainText('合成王老师提供：《本周教学进度》（第1版）');
  const before = await summary.getByRole('region', { name: '变更前后对比', exact: true }).textContent();
  await a.reload();
  assert.equal(new URL(a.url()).pathname, pathA);
  await expect(card(a, '保存班级工作小结').getByRole('region', { name: '变更前后对比', exact: true })).toHaveText(before);
  await confirm(a, card(a, '保存班级工作小结'), true);
  const saved = card(a, '保存班级工作小结');
  const savedText = await saved.getByRole('region', { name: '变更前后对比', exact: true }).textContent();
  await a.reload();
  await expect(card(a, '保存班级工作小结').getByRole('region', { name: '变更前后对比', exact: true })).toHaveText(savedText);
  await expect(a.getByRole('region', { name: '材料协作', exact: true })).toContainText('小结已保存');
  assert.equal(await card(a, '保存班级工作小结').count(), 1);
  await a.screenshot({ path: '../../test-results/collaboration-summary-wide.png', fullPage: true });
  await a.setViewportSize({ width: 390, height: 844 });
  assert(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await a.screenshot({ path: '../../test-results/collaboration-summary-narrow.png', fullPage: true });
  await b.getByRole('button', { name: '设置', exact: true }).click();
  const settingsB = b.getByRole('dialog', { name: '设置', exact: true });
  await settingsB.getByRole('button', { name: '停止协作', exact: true }).click();
  await settingsB.getByRole('button', { name: '确认停止', exact: true }).click();
  await expect(settingsB).toContainText('已停止协作');
  await settingsB.getByRole('button', { name: '关闭设置', exact: true }).click();
  await expect(b.getByRole('region', { name: '材料协作', exact: true })).toContainText('已停止协作', { timeout: 15000 });
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS two original workspaces: human pairing -> request preview -> colleague material preview -> received source-bound summary -> refresh -> lost save response -> receipt recovery -> identical saved result; background attention preserves another draft');
} catch (error) {
  for (const context of browser.contexts()) for (const page of context.pages()) console.error(await page.locator('body').innerText());
  throw error;
} finally { await browser.close(); }
