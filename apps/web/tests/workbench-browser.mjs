import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(), errors = [], external = [], writes = [], discovery = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
  const path = new URL(request.url()).pathname;
  if (!['GET', 'HEAD'].includes(request.method())) writes.push(path);
  if (path.endsWith('/capabilities')) discovery.push(path);
});
try {
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.getByLabel('输入消息').waitFor();
  await page.getByRole('button', { name: '学生', exact: true }).click();
  await page.getByRole('heading', { name: '学生', exact: true }).waitFor();
  assert.equal(await page.locator('.r1-auth').count(), 0);
  await page.reload();
  await page.getByRole('heading', { name: '学生', exact: true }).waitFor();
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('button', { name: '查看操作记录', exact: true }).click();
  await page.getByRole('dialog').getByText('查看文档 · 已通过', { exact: true }).waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByText('完整导出暂不可用。', { exact: false }).waitFor();
  assert.equal(await page.getByRole('button', { name: /生成.*退出包/ }).count(), 0);
  assert(discovery.some(path => path.endsWith('/workbench-d2/capabilities')));
  assert.equal(writes.filter(path => !path.startsWith('/api/identity/')).length, 0);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS original D2 discovery/student/reload/audit and refused partial exit; no business writes or external requests');
} finally { await context.close(); await browser.close(); }
