import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Disposable synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [], external = [], failures = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url()); });
  page.on('response', response => { if (response.status() >= 400) failures.push([response.status(), new URL(response.url()).pathname]); });
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息');
  const send = async text => {
    await input.fill(text);
    await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeEnabled();
    await input.press('Enter');
  };
  const card = title => page.getByRole('region', { name: '对话中的操作候选' })
    .filter({ has: page.getByRole('heading', { name: title, exact: true }) }).last();
  const confirm = async current => {
    try { await current.getByRole('button', { name: '预览这项操作', exact: true }).click(); }
    catch (error) { throw new Error(JSON.stringify({ body: await page.locator('body').innerText(), failures, errors }), { cause: error }); }
    const dialog = page.getByRole('dialog', { name: '确认这次变更', exact: true });
    await dialog.waitFor();
    await dialog.getByRole('button', { name: '明确批准并提交', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await current.getByRole('status').filter({ hasText: '已保存' }).waitFor();
  };
  await send('以后持续整理班级小结，需要核对班会主题。');
  await confirm(card('持续整理班级小结'));
  await input.fill('这是未发送的草稿');
  await page.getByRole('navigation', { name: '主要工作组件' }).getByRole('button', { name: '学生', exact: true }).click();
  await page.getByRole('navigation', { name: '主要工作组件' }).getByRole('button', { name: '对话', exact: true }).click();
  await expect(input).toHaveValue('这是未发送的草稿');
  await page.getByRole('article', { name: '助手回复', exact: true }).getByText('班会主题是什么？', { exact: true }).waitFor({ timeout: 25000 });
  assert.equal(await page.getByRole('article', { name: '你的消息', exact: true }).count(), 1, 'No fabricated user message for the proactive check');
  await expect(input).toHaveValue('这是未发送的草稿');
  await send('班会主题是合作。');
  const first = card('创建工作文档');
  await first.getByText('老师补充：班会主题是合作。', { exact: false }).waitFor();
  await confirm(first);
  const summary = await first.getByRole('region', { name: '变更前后对比', exact: true }).textContent();
  const path = new URL(page.url()).pathname;
  await page.reload(); await input.waitFor();
  await expect(card('创建工作文档').getByRole('region', { name: '变更前后对比', exact: true })).toHaveText(summary);
  assert.equal(new URL(page.url()).pathname, path);
  await send('以后用三条要点整理小结。');
  await confirm(card('调整小结委托'));
  const revised = card('修改工作文档');
  await revised.waitFor({ timeout: 25000 });
  const comparison = revised.getByRole('region', { name: '变更前后对比', exact: true });
  await expect(comparison.getByLabel('修改前', { exact: true })).toContainText('老师补充');
  await expect(comparison.getByLabel('待确认的结果', { exact: true })).toContainText('合成作品核对');
  await expect(comparison.getByLabel('待确认的结果', { exact: true })).toContainText('班会主题是合作');
  await confirm(revised);
  await page.screenshot({ path: '../../test-results/personal-summary-wide.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.screenshot({ path: '../../test-results/personal-summary-narrow.png', fullPage: true });
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS standing delegation -> proactive question -> draft preserved across pages -> answer -> real preview/save -> refresh -> lasting feedback -> proactive three-point revision');
} finally { await browser.close(); }
