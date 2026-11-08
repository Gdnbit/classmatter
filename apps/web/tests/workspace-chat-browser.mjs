import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage(), errors = [], posts = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
    if (request.method() === 'POST') posts.push(new URL(request.url()).pathname);
  });
  await page.goto(base);
  await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息');
  await input.fill('合成无班级第一轮');
  await input.click();
  const expectNoInnerFrame = async () => {
    const style = await input.evaluate(element => { const css = getComputedStyle(element); return { outline: css.outlineStyle, border: css.borderTopWidth, shadow: css.boxShadow }; });
    assert.deepEqual(style, { outline: 'none', border: '0px', shadow: 'none' });
    assert.equal(await page.locator('.r1-composer').evaluate(element => getComputedStyle(element).borderTopWidth), '1px');
  };
  await expectNoInnerFrame();
  await input.press('Shift+Tab'); await page.keyboard.press('Tab');
  assert.equal(await input.evaluate(element => element === document.activeElement), true);
  await expectNoInnerFrame();
  assert.equal(await page.getByLabel('Agent 交互模式').inputValue(), 'chat');
  await page.getByRole('button', { name: '发送消息' }).click();
  await page.locator('article.assistant').getByText('合成无班级聊天回复', { exact: true }).waitFor();
  await input.fill('合成无班级第二轮'); await input.press('Enter');
  await page.waitForFunction(() => document.querySelectorAll('article.assistant').length === 2);
  assert.equal(posts.filter(path => path.endsWith('/workspace-conversations')).length, 1);
  assert.equal(posts.filter(path => path.endsWith('/agent/events')).length, 2);
  await page.getByLabel('Agent 交互模式').selectOption('read');
  await input.fill('没有班级时不可查询');
  assert.equal(await page.getByRole('button', { name: '发送消息' }).isDisabled(), true);
  await page.getByLabel('Agent 交互模式').selectOption('chat');
  await input.fill(''); await page.reload(); await input.waitFor();
  assert.equal(await page.locator('article.assistant').count(), 0);
  assert.equal(posts.filter(path => path.endsWith('/agent/events')).length, 2);
  assert(posts.every(path => path.startsWith('/api/identity/') || /\/agent\/(workspace-conversations|events|conversations\/[^/]+\/forget)$/.test(path)));
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS original UI + actual HTTP/ISB/QG/PG/SDK: no-class multi-turn chat, no class writes, scoped query refused, reload does not replay');
} finally { await browser.close(); }
