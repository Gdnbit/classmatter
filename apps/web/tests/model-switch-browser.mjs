import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
let page;
try {
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], starts = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/events')) starts.push(r.url()) });
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息'); await input.fill('切换期间保留的未发送草稿');
  await page.getByRole('button', { name: '切换模型', exact: true }).click();
  const menu = page.getByRole('region', { name: '选择模型', exact: true });
  await menu.getByLabel('切换后的模型名称').fill('synthetic-switched');
  await menu.getByRole('button', { name: '预览切换模型', exact: true }).click();
  const preview = page.getByRole('dialog');
  await preview.getByRole('button', { name: '明确批准并提交', exact: true }).click();
  await preview.waitFor({ state: 'hidden' });
  assert.equal(await input.inputValue(), '切换期间保留的未发送草稿');
  assert.equal(starts.length, 0);
  await page.getByRole('button', { name: '切换模型', exact: true }).click();
  await menu.getByText('synthetic-switched', { exact: true }).waitFor();
  await menu.getByRole('button', { name: '测试并启用', exact: true }).click();
  await menu.waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '切换模型', exact: true }).filter({ hasText: 'synthetic-switched' }).waitFor();
  assert.equal(await input.inputValue(), '切换期间保留的未发送草稿');
  await input.fill('合成新模型对话');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await page.getByRole('region', { name: '已保存的对话' }).getByText('合成模型切换后回复', { exact: true }).waitFor();
  const answer = page.getByRole('article', { name: '助手回复' }).last();
  await answer.getByRole('heading', { name: '合成模型切换后回复', exact: true }).waitFor();
  assert.equal(await answer.getByRole('heading', { name: '目标', exact: true }).count(), 1);
  assert.deepEqual(await answer.locator('li').allTextContents(), ['平均分', '说出一份']);
  assert.equal(await answer.locator('script,img,iframe').count(), 0);
  assert.equal(await answer.getByRole('button', { name: '复制回答', exact: true }).count(), 1);
  const chat = page.url();await page.reload();
  await page.getByRole('article', { name: '助手回复' }).getByRole('heading', { name: '目标', exact: true }).waitFor();
  assert.equal(page.url(), chat);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.equal(starts.length, 1);
  assert.deepEqual(errors, []);
  console.log('PASS original composer: existing-key model switch via BCG, explicit probe+enable, draft preserved and subsequent SDK chat uses new model');
} catch (error) {
  console.error('Owned model-switch fixture failed', await page?.locator('body').evaluate(element => {
    const copy = element.cloneNode(true); copy.querySelectorAll('input,textarea,pre').forEach(node => node.remove()); return copy.textContent;
  }));
  throw error;
} finally { await browser.close() }
