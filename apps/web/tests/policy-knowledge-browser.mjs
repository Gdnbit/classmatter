import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Disposable fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [], external = [], writes = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
    if (request.method() === 'POST' && /\/commands\/(commit|preview)$/.test(new URL(request.url()).pathname)) writes.push(request.url());
  });
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息');
  await input.waitFor();
  const questions = [
    ['宁乡县初中进校园活动有什么减负依据？', '不得给中小学强制安排与教育教学无关的活动和工作', '第五部分第15条'],
    ['宁乡幼儿园课后服务依据是什么？', '没有找到可引用的具体依据', '地区或学段不符'],
    ['宁乡一中办公室内部报销上限是多少？', '缺少资料不代表不存在相关规定', '内部制度'],
  ];
  for (const [index, [question, expected, locator]] of questions.entries()) {
    await input.fill(question);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const answer = page.getByRole('article', { name: '助手回复', exact: true }).nth(index);
    await answer.getByText(expected, { exact: false }).waitFor({ timeout: 20000 });
    assert((await answer.innerText()).includes(locator));
    const before = await answer.innerText();
    const path = new URL(page.url()).pathname;
    await page.reload();
    await input.waitFor();
    const reloaded = page.getByRole('article', { name: '助手回复', exact: true }).nth(index);
    await reloaded.getByText(expected, { exact: false }).waitFor();
    assert.equal(await reloaded.innerText(), before);
    assert.equal(new URL(page.url()).pathname, path);
    assert.equal(await page.getByRole('region', { name: '对话中的操作候选' }).count(), 0);
    if (index === 0) {
      await page.screenshot({ path: '../../test-results/ningxiang-policy-evidence-wide.png', fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await page.screenshot({ path: '../../test-results/ningxiang-policy-evidence-narrow.png', fullPage: true });
      await page.setViewportSize({ width: 1440, height: 900 });
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.screenshot({ path: '../../test-results/ningxiang-policy-chat.png', fullPage: true });
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  assert.deepEqual(writes, []);
} finally {
  await browser.close();
}
